// HiperTracker: a "Location" on __DT__ (latitude / longitude picked on a map), used for trip-plan stops.
frappe.ui.form.on("__DT__", {
	refresh(frm) {
		ht_loc_draw(frm);
	},
	ht_latitude(frm) { ht_loc_sync(frm); },
	ht_longitude(frm) { ht_loc_sync(frm); },
});

function ht_loc_set(frm, lat, lon) {
	frm.set_value("ht_latitude", Number(Number(lat).toFixed(7)));
	frm.set_value("ht_longitude", Number(Number(lon).toFixed(7)));
}

function ht_loc_draw(frm) {
	const f = frm.fields_dict.ht_location_map;
	if (!f) return;
	const can = frm.perm && frm.perm[0] && frm.perm[0].write;
	f.$wrapper.html(
		'<div class="ht-loc-bar" style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px">' +
		(can ? '<button class="btn btn-xs btn-default" data-a="here">' + __("Use my current location") + "</button>" +
			'<button class="btn btn-xs btn-default" data-a="link">' + __("Paste Google Maps link") + "</button>" : "") +
		'<button class="btn btn-xs btn-default" data-a="open">' + __("Open in Google Maps") + "</button>" +
		(can ? '<button class="btn btn-xs btn-default" data-a="clear">' + __("Clear") + "</button>" : "") + "</div>" +
		'<div class="ht-loc-map" style="height:300px;border-radius:10px;overflow:hidden;border:1px solid var(--border-color)"></div>' +
		'<div class="text-muted small" style="margin-top:6px">' +
		(can ? __("Click the map to set where this is. Field staff trips use this location.") : "") + "</div>");
	f.$wrapper.find("[data-a]").on("click", (e) => {
		e.preventDefault();
		const a = $(e.currentTarget).attr("data-a");
		if (a === "here") {
			if (!navigator.geolocation) return frappe.msgprint(__("This browser can't give a location."));
			frappe.show_alert(__("Getting your location…"));
			navigator.geolocation.getCurrentPosition(
				(p) => ht_loc_set(frm, p.coords.latitude, p.coords.longitude),
				() => frappe.msgprint(__("Could not get your location. Allow location for this site and try again.")),
				{ enableHighAccuracy: true, timeout: 15000 });
		} else if (a === "link") {
			frappe.prompt({ fieldname: "link", fieldtype: "Data", label: __("Google Maps link or 'lat, lon'"), reqd: 1 }, (v) => {
				const t = decodeURIComponent(v.link);
				const m = t.match(/@(-?\d+\.\d+),(-?\d+\.\d+)/) || t.match(/[?&](?:q|query|ll|destination)=(-?\d+\.\d+),\s*(-?\d+\.\d+)/) ||
					t.match(/!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)/) || t.match(/^\s*(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)\s*$/);
				if (!m) return frappe.msgprint(__("Could not find a location in that link. For short links (maps.app.goo.gl), open the link first and copy the full address bar."));
				ht_loc_set(frm, m[1], m[2]);
			}, __("Set location"));
		} else if (a === "open") {
			if (!frm.doc.ht_latitude) return frappe.msgprint(__("No location set yet."));
			window.open("https://www.google.com/maps?q=" + frm.doc.ht_latitude + "," + frm.doc.ht_longitude, "_blank");
		} else if (a === "clear") {
			frm.set_value("ht_latitude", null);
			frm.set_value("ht_longitude", null);
		}
	});
	ht_loc_leaflet().then(() => {
		const L = window.L;
		const has = frm.doc.ht_latitude && frm.doc.ht_longitude;
		const map = L.map(f.$wrapper.find(".ht-loc-map")[0]).setView(has ? [frm.doc.ht_latitude, frm.doc.ht_longitude] : [10.55, 76.3], has ? 16 : 7);
		const base = L.tileLayer("https://{s}.google.com/vt/lyrs=m&hl=en&x={x}&y={y}&z={z}", {
			subdomains: ["mt0", "mt1", "mt2", "mt3"], maxZoom: 20, attribution: "Map data &copy; Google" }).addTo(map);
		const sat = L.tileLayer("https://{s}.google.com/vt/lyrs=y&hl=en&x={x}&y={y}&z={z}", {
			subdomains: ["mt0", "mt1", "mt2", "mt3"], maxZoom: 20, attribution: "Imagery &copy; Google" });
		L.control.layers({ Map: base, Satellite: sat }, null, { position: "topright" }).addTo(map);
		if (can) map.on("click", (e) => ht_loc_set(frm, e.latlng.lat, e.latlng.lng));
		frm.__ht_loc_map = map;
		frm.__ht_loc_pin = null;
		ht_loc_sync(frm);
		setTimeout(() => map.invalidateSize(), 300);
		// the map sits in a tab that may be hidden at first
		$(frm.wrapper).off("shown.bs.tab.htloc").on("shown.bs.tab.htloc", () => setTimeout(() => map.invalidateSize(), 50));
	}).catch(() => f.$wrapper.find(".ht-loc-map").html('<div class="text-muted" style="padding:16px">' + __("The map could not load. You can still type the latitude and longitude.") + "</div>"));
}

function ht_loc_sync(frm) {
	const map = frm.__ht_loc_map, L = window.L;
	if (!map || !L) return;
	const d = frm.doc;
	if (!(d.ht_latitude && d.ht_longitude)) {
		if (frm.__ht_loc_pin) { map.removeLayer(frm.__ht_loc_pin); frm.__ht_loc_pin = null; }
		return;
	}
	const ll = [d.ht_latitude, d.ht_longitude];
	if (!frm.__ht_loc_pin) {
		frm.__ht_loc_pin = L.circleMarker(ll, { radius: 9, color: "#fff", weight: 3, fillColor: "#dc2626", fillOpacity: 1 }).addTo(map);
	} else {
		frm.__ht_loc_pin.setLatLng(ll);
	}
	map.setView(ll, Math.max(map.getZoom(), 15));
}

function ht_loc_leaflet() {
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
