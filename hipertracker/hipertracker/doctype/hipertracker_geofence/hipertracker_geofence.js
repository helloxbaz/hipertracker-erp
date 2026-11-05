// HiperTracker Geofence form: pick the place on a map. Click to put the centre; the circle follows the radius.
frappe.ui.form.on("HiperTracker Geofence", {
	refresh(frm) {
		frm.trigger("ht_draw_map");
		frm.add_custom_button(__("Paste Google Maps link"), () => {
			frappe.prompt({ fieldname: "link", fieldtype: "Data", label: "Google Maps link or 'lat, lon'", reqd: 1 }, (v) => {
				const t = decodeURIComponent(v.link);
				const m = t.match(/@(-?\d+\.\d+),(-?\d+\.\d+)/) || t.match(/[?&](?:q|query|ll)=(-?\d+\.\d+),\s*(-?\d+\.\d+)/) ||
					t.match(/!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)/) || t.match(/^\s*(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)\s*$/);
				if (!m) return frappe.msgprint(__("Could not find a location in that link. Short links (maps.app.goo.gl) must be opened first and the full link copied."));
				frm.set_value("latitude", parseFloat(m[1]));
				frm.set_value("longitude", parseFloat(m[2]));
			}, __("Place on map"));
		});
		if (!frm.is_new()) {
			frm.add_custom_button(__("Visits"), () => frappe.set_route("List", "HiperTracker Geofence Visit", { geofence: frm.doc.name }));
		}
	},
	latitude(frm) { frm.trigger("ht_sync"); },
	longitude(frm) { frm.trigger("ht_sync"); },
	radius(frm) { frm.trigger("ht_sync"); },
	color(frm) { frm.trigger("ht_sync"); },

	ht_draw_map(frm) {
		const wrap = frm.fields_dict.map_html && frm.fields_dict.map_html.$wrapper;
		if (!wrap) return;
		wrap.html('<div class="ht-gf-map" style="height:380px;border-radius:10px;overflow:hidden;border:1px solid var(--border-color)"></div>' +
			'<div class="text-muted small" style="margin-top:6px">Click the map to set the centre. Other places are shown in grey.</div>');
		const el = wrap.find(".ht-gf-map")[0];
		ht_leaflet().then(() => {
			const L = window.L;
			const has = frm.doc.latitude && frm.doc.longitude;
			const map = L.map(el).setView(has ? [frm.doc.latitude, frm.doc.longitude] : [10.55, 76.3], has ? 16 : 8);
			const base = L.tileLayer("https://{s}.google.com/vt/lyrs=m&hl=en&x={x}&y={y}&z={z}", {
				subdomains: ["mt0", "mt1", "mt2", "mt3"], maxZoom: 20, attribution: "Map data &copy; Google" }).addTo(map);
			const sat = L.tileLayer("https://{s}.google.com/vt/lyrs=y&hl=en&x={x}&y={y}&z={z}", {
				subdomains: ["mt0", "mt1", "mt2", "mt3"], maxZoom: 20, attribution: "Imagery &copy; Google" });
			L.control.layers({ Map: base, Satellite: sat }, null, { position: "topright" }).addTo(map);
			map.on("click", (e) => {
				if (frm.doc.docstatus > 0 || !frm.perm[0] || !frm.perm[0].write) return;
				frm.set_value("latitude", Number(e.latlng.lat.toFixed(7)));
				frm.set_value("longitude", Number(e.latlng.lng.toFixed(7)));
			});
			frm.__ht_map = map;
			frm.__ht_circle = null;
			frm.trigger("ht_sync");
			setTimeout(() => map.invalidateSize(), 300);
			// the other places, for reference
			frappe.db.get_list("HiperTracker Geofence", { fields: ["name", "latitude", "longitude", "radius"], limit: 500 }).then((rows) => {
				rows.filter((r) => r.name !== frm.doc.name && r.latitude && r.longitude).forEach((r) => {
					L.circle([r.latitude, r.longitude], { radius: r.radius || 200, color: "#9ca3af", weight: 1, fillOpacity: 0.06 })
						.bindTooltip(frappe.utils.escape_html(r.name)).addTo(map);
				});
			});
		}).catch(() => wrap.find(".ht-gf-map").html('<div class="text-muted" style="padding:20px">The map could not load. You can still type the latitude and longitude.</div>'));
	},

	ht_sync(frm) {
		const map = frm.__ht_map, L = window.L;
		if (!map || !L) return;
		const d = frm.doc;
		if (!(d.latitude && d.longitude)) return;
		const ll = [d.latitude, d.longitude];
		const r = d.radius || 200;
		const color = d.color || "#0ea5e9";
		if (!frm.__ht_circle) {
			frm.__ht_circle = L.circle(ll, { radius: r, color: color, weight: 2, fillOpacity: 0.15 }).addTo(map);
			frm.__ht_dot = L.circleMarker(ll, { radius: 5, color: "#fff", weight: 2, fillColor: color, fillOpacity: 1 }).addTo(map);
		} else {
			frm.__ht_circle.setLatLng(ll).setRadius(r).setStyle({ color: color });
			frm.__ht_dot.setLatLng(ll).setStyle({ fillColor: color });
		}
		map.fitBounds(frm.__ht_circle.getBounds(), { padding: [30, 30], maxZoom: 18 });
	},
});

function ht_leaflet() {
	if (!document.getElementById("ht-leaflet-css")) {
		const css = document.createElement("link");
		css.id = "ht-leaflet-css";
		css.rel = "stylesheet";
		css.href = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css";
		document.head.appendChild(css);
	}
	if (window.L && window.L.map) return Promise.resolve();
	return new Promise((resolve, reject) => {
		let s = document.getElementById("ht-leaflet-js");
		if (!s) {
			s = document.createElement("script");
			s.id = "ht-leaflet-js";
			s.src = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js";
			document.head.appendChild(s);
		}
		s.addEventListener("error", () => reject(new Error("Map library could not load")));
		const t = setInterval(() => { if (window.L && window.L.map) { clearInterval(t); resolve(); } }, 200);
	});
}
