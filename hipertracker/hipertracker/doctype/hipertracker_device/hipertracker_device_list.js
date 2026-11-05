// Generated from map_block/htmini.js + map_block/device_list.src.js - edit those and rebuild.
// Shared helpers for the HiperTracker Device form and list maps (kept in sync in both scripts).
// versioned: a newer copy (from either script) replaces an older one already on the page
window.htmini = window.htmini && window.htmini.v >= 2 ? window.htmini : (function () {
	const COLORS = { online: "#16a34a", offline: "#dc2626", gps_off: "#d97706", off_duty: "#9ca3af", unknown: "#6b7280" };
	const LABELS = { online: "Online", offline: "Offline", gps_off: "GPS Off", off_duty: "Off duty", unknown: "No data" };
	const esc = (s) => frappe.utils.escape_html(s == null ? "" : String(s));
	const ago = (min) => {
		if (min == null) return "—";
		if (min < 1) return "just now";
		if (min < 60) return Math.round(min) + " min ago";
		if (min < 1440) return Math.round(min / 60) + " h ago";
		return Math.round(min / 1440) + " d ago";
	};
	const place = (d) =>
		d.address || (d.lat != null ? Number(d.lat).toFixed(5) + ", " + Number(d.lon).toFixed(5) : "—");
	const badge = (status) =>
		'<span style="display:inline-flex;align-items:center;gap:5px;padding:2px 9px;border-radius:999px;font-size:12px;font-weight:500;color:' +
		COLORS[status] + ";background:" + COLORS[status] + '1f"><span style="width:7px;height:7px;border-radius:50%;background:' +
		COLORS[status] + '"></span>' + LABELS[status] + "</span>";

	let leafletPromise = null;
	function leaflet() {
		if (!document.getElementById("ht-leaflet-css")) {
			const css = document.createElement("link");
			css.id = "ht-leaflet-css";
			css.rel = "stylesheet";
			css.href = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css";
			document.head.appendChild(css);
		}
		if (window.L && window.L.map) return Promise.resolve();
		if (!leafletPromise) {
			leafletPromise = new Promise((resolve, reject) => {
				let s = document.getElementById("ht-leaflet-js");
				if (!s) {
					s = document.createElement("script");
					s.id = "ht-leaflet-js";
					s.src = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js";
					document.head.appendChild(s);
				}
				s.addEventListener("load", () => resolve());
				s.addEventListener("error", () => reject(new Error("Map library could not load")));
				const t = setInterval(() => {
					if (window.L && window.L.map) { clearInterval(t); resolve(); }
				}, 200);
			});
		}
		return leafletPromise;
	}

	function makeMap(el) {
		const L = window.L;
		const map = L.map(el).setView([10.55, 76.3], 8);
		// Google road / hybrid tiles, the same layers Traccar uses
		const base = L.tileLayer("https://{s}.google.com/vt/lyrs=m&hl=en&x={x}&y={y}&z={z}", {
			subdomains: ["mt0", "mt1", "mt2", "mt3"], maxZoom: 20, attribution: "Map data &copy; Google" }).addTo(map);
		const sat = L.tileLayer("https://{s}.google.com/vt/lyrs=y&hl=en&x={x}&y={y}&z={z}", {
			subdomains: ["mt0", "mt1", "mt2", "mt3"], maxZoom: 20, attribution: "Imagery &copy; Google" });
		L.control.layers({ Map: base, Satellite: sat }, null, { position: "topright" }).addTo(map);
		setTimeout(() => map.invalidateSize(), 250);
		return map;
	}

	function marker(d, onClick) {
		const L = window.L;
		const color = COLORS[d.status] || COLORS.unknown;
		const m = L.circleMarker([d.lat, d.lon], { radius: 9, color: "#fff", weight: 3, fillColor: color, fillOpacity: 1 });
		update(m, d);
		if (onClick) m.on("click", () => onClick(d));
		return m;
	}

	function update(m, d) {
		const color = COLORS[d.status] || COLORS.unknown;
		m.setLatLng([d.lat, d.lon]);
		m.setStyle({ fillColor: color });
		const sub = d.status === "gps_off" ? "GPS switched off"
			: d.status === "off_duty" ? "Off duty"
			: (d.speed || 0) + " km/h" + (d.status === "online" ? "" : " • " + ago(d.age_minutes));
		const html = "<b>" + esc(d.label) + "</b>" + (d.employee_name && d.employee_name !== d.label ? " · " + esc(d.employee_name) : "") +
			'<br><span style="color:' + color + '">' + sub + "</span>";
		if (m.getTooltip()) m.setTooltipContent(html);
		else m.bindTooltip(html, { direction: "top", offset: [0, -8] }); // name shows on hover / tap
	}

	// One day's route from hipertracker_history: blue line, green start, red last point,
	// check in / out rings and orange rings where GPS was switched off. Returns the layer group.
	function drawRoute(map, data) {
		const L = window.L;
		const g = L.layerGroup().addTo(map);
		const pts = (data.points || []).map((p) => [p[0], p[1]]);
		const dot = (ll, color, tip, ring) =>
			L.circleMarker(ll, ring
				? { radius: 9, color: color, weight: 3, fillOpacity: 0 }
				: { radius: 6, color: "#fff", weight: 2, fillColor: color, fillOpacity: 1 }).bindTooltip(tip).addTo(g);
		if (pts.length) {
			L.polyline(pts, { color: "#2563eb", weight: 4, opacity: 0.85 }).addTo(g);
			dot(pts[0], "#16a34a", "Start " + data.points[0][2]);
			dot(pts[pts.length - 1], "#dc2626", "Last " + data.points[data.points.length - 1][2]);
		}
		const extra = [];
		(data.checkins || []).forEach((c) => {
			if (c.lat == null) return;
			extra.push([c.lat, c.lon]);
			dot([c.lat, c.lon], c.log_type === "IN" ? "#16a34a" : "#6b7280", (c.log_type === "IN" ? "Checked in " : "Checked out ") + String(c.time).slice(11, 16), true);
		});
		(data.events || []).forEach((e) => {
			if (e.lat == null || e.event === "GPS On") return;
			dot([e.lat, e.lon], COLORS.gps_off, e.event + " " + String(e.time).slice(11, 16), true);
		});
		// stops: purple P markers
		(data.stops || []).forEach((st) => {
			L.circleMarker([st.lat, st.lon], { radius: 10, color: "#fff", weight: 2, fillColor: "#7c3aed", fillOpacity: 1 })
				.bindTooltip("Stopped " + mins(st.minutes) + " (" + st.start + " – " + (st.ongoing ? "now" : st.end) + ")")
				.addTo(g);
		});
		// over the speed limit: red markers at the top speed of each spell
		(data.speeding || []).forEach((sp) => {
			L.circleMarker([sp.lat, sp.lon], { radius: 8, color: "#fff", weight: 2, fillColor: "#dc2626", fillOpacity: 1 })
				.bindTooltip("Over speed " + sp.max_speed + " km/h (" + sp.start + (sp.end !== sp.start ? " – " + sp.end : "") + ")")
				.addTo(g);
		});
		const all = pts.concat(extra);
		if (all.length > 1) map.fitBounds(all, { padding: [40, 40], maxZoom: 16 });
		else if (all.length) map.setView(all[0], 15);
		return g;
	}

	const mins = (m) => (m >= 60 ? Math.floor(m / 60) + "h " + String(m % 60).padStart(2, "0") + "m" : m + " min");

	function routeSummary(data) {
		const n = (data.points || []).length;
		if (!n) return "No route recorded on " + esc(frappe.datetime.str_to_user(data.date)) + ".";
		const off = (data.events || []).filter((e) => e.event === "GPS Off").length;
		return "<b>" + esc(frappe.datetime.str_to_user(data.date)) + "</b>: " + data.distance_km + " km, " +
			(data.trips || []).length + " trip(s), " + (data.stops || []).length + " stop(s) · moving " +
			mins(data.moving_minutes || 0) + ", stopped " + mins(data.stopped_minutes || 0) +
			(off ? ' · <b style="color:' + COLORS.gps_off + '">GPS switched off ' + off + " time(s)</b>" : "") +
			((data.speeding || []).length ? ' · <b style="color:#dc2626">Over ' + data.speed_limit + " km/h " + data.speeding.length + " time(s)</b>" : "");
	}

	// trips and stops in time order, as a small table under the map
	function routeTable(data) {
		const rows = [];
		(data.trips || []).forEach((t) => rows.push([t.start,
			'<span style="color:#2563eb">&#10148; Trip</span>', t.start + " – " + t.end,
			t.distance_km + " km · " + mins(t.minutes) + " · avg " + t.avg_speed + " / max " + t.max_speed + " km/h"]));
		(data.stops || []).forEach((st) => rows.push([st.start,
			'<span style="color:#7c3aed">&#9208; Stop</span>', st.start + " – " + (st.ongoing ? "now" : st.end),
			mins(st.minutes) + ' · <a target="_blank" rel="noopener" href="https://www.google.com/maps?q=' + st.lat + "," + st.lon + '">map</a>']));
		(data.speeding || []).forEach((sp) => rows.push([sp.start,
			'<span style="color:#dc2626">&#9888; Over speed</span>', sp.start + (sp.end !== sp.start ? " – " + sp.end : ""),
			"top " + sp.max_speed + " km/h (limit " + data.speed_limit + ') · <a target="_blank" rel="noopener" href="https://www.google.com/maps?q=' + sp.lat + "," + sp.lon + '">map</a>']));
		if (!rows.length) return "";
		rows.sort((a, b) => (a[0] < b[0] ? -1 : 1));
		return '<table class="table table-sm" style="margin-top:8px;font-size:13px"><tbody>' +
			rows.map((r) => "<tr><td>" + r[1] + "</td><td>" + r[2] + "</td><td>" + r[3] + "</td></tr>").join("") + "</tbody></table>";
	}

	return { v: 3, COLORS, LABELS, esc, ago, place, badge, leaflet, makeMap, marker, update, drawRoute, routeSummary, routeTable };
})();

// HiperTracker Device list: live map of all devices above the list.
var HT_LIST_METHOD = "hipertracker_live";

frappe.listview_settings["HiperTracker Device"] = {
	add_fields: ["last_status", "traccar_identifier", "employee_name"],
	get_indicator(doc) {
		const map = { Online: "green", Offline: "red", "GPS Off": "orange", "Off Duty": "gray", "No Data": "gray", "Not in Traccar": "gray" };
		if (doc.last_status) return [__(doc.last_status), map[doc.last_status] || "gray", "last_status,=," + doc.last_status];
	},
	onload(listview) {
		listview.page.add_inner_button(__("Full Map"), () => frappe.set_route("hipertracker"));
		ht_list_render(listview, 0);
		if (window.__ht_list_timer) clearInterval(window.__ht_list_timer);
		window.__ht_list_timer = setInterval(() => {
			const route = frappe.get_route();
			if (route[0] !== "List" || route[1] !== "HiperTracker Device") {
				clearInterval(window.__ht_list_timer);
				window.__ht_list_timer = null;
				return;
			}
			if (document.visibilityState === "visible") ht_list_render(listview, 0);
		}, 30000);
	},
};

function ht_list_render(listview, sync) {
	const H = window.htmini;
	let box = listview.page.main.find(".ht-lmap");
	if (!box.length) {
		box = $(
			'<div class="ht-lmap" style="padding:12px 15px 4px">' +
				'<div class="ht-lsum" style="display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center;font-size:13px;margin-bottom:10px"></div>' +
				'<div class="ht-lcanvas" style="height:380px;border-radius:12px;overflow:hidden;border:1px solid var(--border-color)"></div>' +
			"</div>"
		);
		listview.page.main.prepend(box);
	}
	const sum = box.find(".ht-lsum");
	return frappe.call({ method: HT_LIST_METHOD, args: { sync: sync ? 1 : 0 } }).then((r) => {
		const data = r.message || {};
		if (data.error) {
			sum.html('<span class="text-danger">' + H.esc(data.error) + '</span> <a href="javascript:void(0)" onclick="frappe.set_route(\'Form\', \'HiperTracker Settings\')">Open Settings</a>');
			box.find(".ht-lcanvas").hide();
			return data;
		}
		const ds = data.devices || [];
		const c = { online: 0, offline: 0, gps_off: 0, off_duty: 0 };
		ds.forEach((d) => {
			if (d.status === "online") c.online++;
			else if (d.status === "gps_off") c.gps_off++;
			else if (d.status === "off_duty") c.off_duty++;
			else c.offline++;
		});
		const gps = ds.filter((d) => d.status === "gps_off");
		sum.html(
			"<b>" + ds.length + " device(s)</b>" +
				H.badge("online") + " " + c.online + H.badge("offline") + " " + c.offline + H.badge("gps_off") + " " + c.gps_off + (c.off_duty ? H.badge("off_duty") + " " + c.off_duty : "") +
				(gps.length ? '<span style="color:' + H.COLORS.gps_off + '"><b>GPS off:</b> ' +
					gps.map((d) => H.esc(d.label) + (d.employee_name ? " (" + H.esc(d.employee_name) + ")" : "")).join(", ") + "</span>" : "") +
				((data.not_in_traccar || []).length ? '<span class="text-muted">Waiting for the first location: ' +
					data.not_in_traccar.map((x) => H.esc(x.label)).join(", ") + "</span>" : "") +
				(!ds.length ? '<span class="text-muted">No phones yet. Click <b>+ Add HiperTracker Device</b>, then scan its setup QR with the phone.</span>' : "")
		);
		box.find(".ht-lcanvas").show();
		return H.leaflet().then(() => {
			const el = box.find(".ht-lcanvas")[0];
			let first = false;
			if (!el.__htmap) {
				el.__htmap = H.makeMap(el);
				el.__htmarkers = {};
				first = true;
			}
			const map = el.__htmap;
			const keep = {};
			ds.forEach((d) => {
				if (d.lat == null) return;
				const key = String(d.identifier);
				keep[key] = 1;
				if (el.__htmarkers[key]) H.update(el.__htmarkers[key], d);
				else {
					el.__htmarkers[key] = H.marker(d, (x) => frappe.set_route("Form", "HiperTracker Device", x.record)).addTo(map);
				}
			});
			Object.keys(el.__htmarkers).forEach((k) => {
				if (!keep[k]) { map.removeLayer(el.__htmarkers[k]); delete el.__htmarkers[k]; }
			});
			if (first) {
				const pts = ds.filter((d) => d.lat != null).map((d) => [d.lat, d.lon]);
				if (pts.length > 1) map.fitBounds(pts, { padding: [50, 50], maxZoom: 13 });
				else if (pts.length === 1) map.setView(pts[0], 13);
			}
			setTimeout(() => map.invalidateSize(), 200);
			return data;
		});
	});
}
