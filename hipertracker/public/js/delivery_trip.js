// HiperTracker on the Delivery Trip form: planned stops vs the route the vehicle / driver actually took.
frappe.ui.form.on("Delivery Trip", {
	refresh(frm) {
		frm.$wrapper.find(".ht-dt").remove();
		clearInterval(frm.__ht_timer);
		if (frm.is_new() || !frm.doc.departure_time) return;
		const box = $('<div class="ht-dt" style="margin:0 0 16px;padding:14px 16px;border:1px solid var(--border-color);border-radius:12px;background:var(--card-bg)">' +
			'<div style="display:flex;align-items:center;gap:10px;margin-bottom:8px"><b style="font-size:15px">Live tracking</b>' +
			'<span class="ht-dt-sum text-muted small" style="flex:1"></span>' +
			'<button class="btn btn-xs btn-default ht-dt-ref">Refresh</button></div>' +
			'<div class="ht-dt-map" style="height:340px;border-radius:10px;overflow:hidden"></div>' +
			'<div class="ht-dt-tab" style="margin-top:10px"></div></div>');
		frm.$wrapper.find(".form-layout").first().prepend(box);
		box.find(".ht-dt-ref").on("click", () => ht_dt_load(frm, box));
		ht_dt_leaflet().then(() => ht_dt_load(frm, box))
			.catch(() => box.find(".ht-dt-map").html('<div class="text-muted" style="padding:20px">The map could not load.</div>'));
		// keep it live while the trip is under way
		if (["Scheduled", "In Transit"].includes(frm.doc.status)) {
			frm.__ht_timer = setInterval(() => {
				if (!document.body.contains(box[0])) return clearInterval(frm.__ht_timer);
				if (document.visibilityState === "visible") ht_dt_load(frm, box);
			}, 60000);
		}
	},
});

function ht_dt_load(frm, box) {
	return frappe.call({ method: "hipertracker_delivery_trip", args: { trip: frm.doc.name } }).then((r) => {
		const d = r.message || {};
		const esc = (s) => frappe.utils.escape_html(s == null ? "" : String(s));
		const L = window.L;
		if (!box.__map) {
			box.__map = L.map(box.find(".ht-dt-map")[0]).setView([10.55, 76.3], 8);
			L.tileLayer("https://{s}.google.com/vt/lyrs=m&hl=en&x={x}&y={y}&z={z}", {
				subdomains: ["mt0", "mt1", "mt2", "mt3"], maxZoom: 20, attribution: "Map data &copy; Google" }).addTo(box.__map);
			setTimeout(() => box.__map.invalidateSize(), 300);
		}
		const map = box.__map;
		if (box.__layer) map.removeLayer(box.__layer);
		const g = (box.__layer = L.layerGroup().addTo(map));
		const all = [];
		const pts = (d.points || []).map((p) => [p[0], p[1]]);
		if (pts.length) {
			L.polyline(pts, { color: "#2563eb", weight: 4, opacity: 0.85 }).addTo(g);
			all.push(...pts);
		}
		const colors = { Visited: "#16a34a", "At stop": "#f59e0b", Pending: "#6b7280" };
		(d.stops || []).forEach((s) => {
			if (s.lat == null) return;
			const c = colors[s.status] || "#6b7280";
			L.circle([s.lat, s.lon], { radius: s.radius, color: c, weight: 1, fillOpacity: 0.08 }).addTo(g);
			L.marker([s.lat, s.lon], { icon: L.divIcon({ className: "", iconSize: [0, 0],
				html: '<span style="position:absolute;left:-12px;top:-12px;width:24px;height:24px;border-radius:50%;background:' + c +
					';color:#fff;border:2px solid #fff;font:700 12px/20px sans-serif;text-align:center;box-shadow:0 1px 4px rgba(0,0,0,.35)">' + s.idx + "</span>" }) })
				.bindTooltip("Stop " + s.idx + ": " + esc(s.customer) + " — " + s.status).addTo(g);
			all.push([s.lat, s.lon]);
		});
		if (d.last) {
			L.circleMarker([d.last.lat, d.last.lon], { radius: 8, color: "#fff", weight: 3, fillColor: "#dc2626", fillOpacity: 1 })
				.bindTooltip("Now here (" + String(d.last.time).slice(11, 16) + ")").addTo(g);
			all.push([d.last.lat, d.last.lon]);
		}
		if (all.length > 1) map.fitBounds(all, { padding: [40, 40], maxZoom: 16 });
		else if (all.length) map.setView(all[0], 15);

		const total = (d.stops || []).length;
		let sum;
		if (!d.device) {
			sum = "No HiperTracker phone found for this trip — set the vehicle on a device, or give the driver's employee a device.";
		} else {
			sum = "Tracked by " + esc(d.matched_by) + " · <b>" + d.visited + " of " + total + "</b> stops reached · " +
				"actual <b>" + d.actual_km + " km</b>" + (d.planned_km ? " / planned ~" + d.planned_km + " km" : "") +
				(d.last ? " · last seen " + (d.last.age_minutes < 1 ? "just now" : Math.round(d.last.age_minutes) + " min ago") : " · no locations yet");
		}
		box.find(".ht-dt-sum").html(sum);

		const badge = (s) => {
			const c = { Visited: "green", "At stop": "orange", Pending: "gray", "No location": "red" }[s] || "gray";
			return '<span class="indicator-pill ' + c + '">' + esc(s) + "</span>";
		};
		const rows = (d.stops || []).map((s) => "<tr><td>" + s.idx + "</td><td><b>" + esc(s.customer) + '</b><div class="text-muted small">' +
			esc(s.address) + "</div></td><td>" + badge(s.status) + (s.out_of_order ? ' <span class="text-warning small">out of order</span>' : "") +
			"</td><td>" + (s.eta ? esc(s.eta) : "") + "</td><td>" + (s.arrived ? esc(s.arrived) : "—") + "</td><td>" + (s.left ? esc(s.left) : "—") +
			"</td><td>" + (s.minutes != null ? s.minutes + " min" : "") + "</td><td>" +
			(s.lat == null ? '<a href="#" class="ht-dt-add" data-customer="' + esc(s.customer) + '">Add its location</a>' : "") + "</td></tr>").join("");
		box.find(".ht-dt-tab").html('<table class="table table-sm" style="font-size:13px;margin:0"><thead><tr><th>#</th><th>Customer</th><th>Status</th>' +
			"<th>ETA</th><th>Arrived</th><th>Left</th><th>Time there</th><th></th></tr></thead><tbody>" + rows + "</tbody></table>");
		box.find(".ht-dt-add").on("click", (e) => {
			e.preventDefault();
			const customer = $(e.currentTarget).attr("data-customer");
			frappe.new_doc("HiperTracker Geofence", { geofence_name: customer, place_type: "Customer Site", customer: customer });
		});
	});
}

function ht_dt_leaflet() {
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
