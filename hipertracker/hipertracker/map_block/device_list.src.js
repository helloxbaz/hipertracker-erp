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
