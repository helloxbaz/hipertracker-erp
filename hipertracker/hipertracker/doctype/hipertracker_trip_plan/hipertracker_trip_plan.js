// HiperTracker Trip Plan: plan the stops in order on a map, then follow which were reached and left.
frappe.ui.form.on("HiperTracker Trip Plan", {
	setup(frm) {
		frm.set_query("device", () => ({ filters: { active: 1 } }));
		frm.set_query("reference_doctype", "stops", () => ({ filters: { name: ["in", Object.keys(HTP_VISITS)] } }));
	},
	refresh(frm) {
		clearInterval(frm.__htp_timer);
		if (!frm.is_new()) {
			frm.add_custom_button(__("Recalculate from history"), () =>
				frappe.call({ method: "hipertracker_trip_plan", args: { plan: frm.doc.name, recalc: 1 }, freeze: true })
					.then(() => frm.reload_doc()));
			if (frm.doc.status === "In Progress" || frm.doc.status === "Planned") {
				frm.__htp_timer = setInterval(() => {
					if (frm.doc.doctype !== "HiperTracker Trip Plan" || !document.body.contains(frm.$wrapper[0])) return clearInterval(frm.__htp_timer);
					if (document.visibilityState === "visible" && !frm.is_dirty()) htp_load(frm);
				}, 60000);
			}
		}
		htp_draw(frm);
	},
	employee(frm) {
		if (frm.doc.employee) {
			frappe.db.get_value("HiperTracker Device", { employee: frm.doc.employee, active: 1 }, "name")
				.then((r) => frm.set_value("device", (r.message && r.message.name) || ""));
		}
	},
});

frappe.ui.form.on("HiperTracker Trip Stop", {
	reference_doctype(frm, cdt, cdn) {
		frappe.model.set_value(cdt, cdn, "reference_name", "");
	},
	reference_name(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.reference_doctype || !row.reference_name) return;
		htp_fill_stop(frm, row);
	},
	latitude: (frm) => htp_plan_layer(frm),
	longitude: (frm) => htp_plan_layer(frm),
	radius: (frm) => htp_plan_layer(frm),
	place(frm, cdt, cdn) { setTimeout(() => htp_plan_layer(frm), 600); },
	stops_remove: (frm) => htp_plan_layer(frm),
	stops_move: (frm) => htp_plan_layer(frm),
});

// what a stop can be, the field that holds its name, and its colour on the map
var HTP_VISITS = {
	Customer: ["customer_name", "#2563eb"], Lead: ["lead_name", "#f59e0b"], Opportunity: ["title", "#d946ef"],
	Supplier: ["supplier_name", "#0d9488"], Prospect: ["company_name", "#64748b"], "CRM Lead": ["lead_name", "#f97316"],
	"CRM Deal": ["organization", "#a855f7"], "CRM Organization": ["organization_name", "#0ea5e9"],
};

// take the stop's name and location from the customer / lead / deal (the server does the same on save, with fallbacks)
function htp_fill_stop(frm, row) {
	const dt = row.reference_doctype;
	const tf = (HTP_VISITS[dt] || [])[0];
	frappe.db.get_value(dt, row.reference_name, ["ht_latitude", "ht_longitude"].concat(tf ? [tf] : [])).then((r) => {
		const v = r.message || {};
		frappe.model.set_value(row.doctype, row.name, "stop_name", (tf && v[tf]) || row.reference_name);
		if (v.ht_latitude && v.ht_longitude) {
			frappe.model.set_value(row.doctype, row.name, "latitude", v.ht_latitude);
			frappe.model.set_value(row.doctype, row.name, "longitude", v.ht_longitude);
		} else if (!["Opportunity", "CRM Deal"].includes(dt)) {
			frappe.msgprint(__("{0} {1} has no location yet. {2} to set it on its map, then pick it again.", [__(dt),
				"<b>" + htp_esc(row.reference_name) + "</b>",
				'<a href="/app/' + frappe.router.slug(dt) + "/" + encodeURIComponent(row.reference_name) + '" target="_blank">' + __("Open it") + "</a>"]));
		}
		setTimeout(() => htp_plan_layer(frm), 100);
	});
}

// every customer / lead / deal that has a location, as small dots: click one to add it as the next stop
function htp_records_layer(frm) {
	const map = frm.__htp_map, L = window.L;
	if (!map || frm.__htp_records) return;
	const g = (frm.__htp_records = L.layerGroup().addTo(map));
	Object.keys(HTP_VISITS).forEach((dt) => {
		const tf = HTP_VISITS[dt][0], color = HTP_VISITS[dt][1];
		frappe.db.get_list(dt, { fields: ["name", tf, "ht_latitude", "ht_longitude"], filters: [["ht_latitude", "!=", 0]], limit: 1000 })
			.then((rows) => rows.forEach((r) => {
				if (!r.ht_latitude || !r.ht_longitude) return;
				const label = r[tf] || r.name;
				L.circleMarker([r.ht_latitude, r.ht_longitude], { radius: 6, color: "#fff", weight: 1.5, fillColor: color, fillOpacity: 0.9 })
					.bindTooltip(htp_esc(__(dt)) + ": " + htp_esc(label) + (frm.doc.status === "Planned" || frm.is_new() ? "<br><i>" + __("Click to add as a stop") + "</i>" : ""))
					.on("click", (e) => {
						L.DomEvent.stopPropagation(e);
						if (!(frm.doc.status === "Planned" || frm.is_new()) || !frm.perm[0] || !frm.perm[0].write) return;
						if ((frm.doc.stops || []).some((s) => s.reference_doctype === dt && s.reference_name === r.name)) {
							return frappe.show_alert({ message: __("{0} is already a stop", [label]), indicator: "orange" });
						}
						frm.add_child("stops", { reference_doctype: dt, reference_name: r.name, stop_name: label,
							latitude: r.ht_latitude, longitude: r.ht_longitude, radius: 150 });
						frm.refresh_field("stops");
						htp_plan_layer(frm);
						frappe.show_alert({ message: __("Added {0} as stop {1}", [label, frm.doc.stops.length]), indicator: "green" });
					})
					.addTo(g);
			}))
			.catch(() => {});
	});
}

var HTP_COLORS = { Pending: "#6b7280", Reached: "#f59e0b", Left: "#16a34a", Skipped: "#9ca3af" };
var htp_esc = (s) => frappe.utils.escape_html(s == null ? "" : String(s));

function htp_draw(frm) {
	const wrap = frm.fields_dict.map_html && frm.fields_dict.map_html.$wrapper;
	if (!wrap) return;
	wrap.html('<div class="htp-sum" style="margin-bottom:8px"></div>' +
		'<div class="htp-map" style="height:400px;border-radius:10px;overflow:hidden;border:1px solid var(--border-color)"></div>' +
		'<div class="text-muted small htp-hint" style="margin:6px 0 10px"></div><div class="htp-tab"></div>');
	wrap.find(".htp-hint").text(frm.doc.status === "Planned" || frm.is_new()
		? __("Click a coloured dot (a customer, lead, deal or supplier with a location) to add it as the next stop, or click anywhere to add a point. Stops are visited in the order of the table — drag rows to change it.")
		: __("Grey dashed line: the plan. Blue line: the route actually taken. Red dot: where the phone is now."));
	htp_leaflet().then(() => {
		const L = window.L;
		const map = L.map(wrap.find(".htp-map")[0]).setView([10.55, 76.3], 8);
		const base = L.tileLayer("https://{s}.google.com/vt/lyrs=m&hl=en&x={x}&y={y}&z={z}", {
			subdomains: ["mt0", "mt1", "mt2", "mt3"], maxZoom: 20, attribution: "Map data &copy; Google" }).addTo(map);
		const sat = L.tileLayer("https://{s}.google.com/vt/lyrs=y&hl=en&x={x}&y={y}&z={z}", {
			subdomains: ["mt0", "mt1", "mt2", "mt3"], maxZoom: 20, attribution: "Imagery &copy; Google" });
		L.control.layers({ Map: base, Satellite: sat }, null, { position: "topright" }).addTo(map);
		map.on("click", (e) => {
			if (!frm.perm[0] || !frm.perm[0].write || !["Planned", undefined, ""].includes(frm.doc.status)) return;
			const row = frm.add_child("stops", {
				stop_name: __("Stop {0}", [(frm.doc.stops || []).length + 1]),
				latitude: Number(e.latlng.lat.toFixed(7)), longitude: Number(e.latlng.lng.toFixed(7)), radius: 150,
			});
			frm.refresh_field("stops");
			htp_plan_layer(frm);
			frappe.show_alert({ message: __("Added {0} — give it a name or a time in the table", [row.stop_name]), indicator: "green" });
		});
		frm.__htp_map = map;
		frm.__htp_fit = true;
		frm.__htp_records = null;
		htp_records_layer(frm);
		setTimeout(() => map.invalidateSize(), 300);
		htp_plan_layer(frm);
		if (!frm.is_new()) htp_load(frm);
	}).catch(() => wrap.find(".htp-map").html('<div class="text-muted" style="padding:20px">The map could not load.</div>'));
}

// the plan itself: numbered stops in order, joined by a dashed line
function htp_plan_layer(frm, statuses) {
	const map = frm.__htp_map, L = window.L;
	if (!map) return;
	if (frm.__htp_plan) map.removeLayer(frm.__htp_plan);
	const g = (frm.__htp_plan = L.layerGroup().addTo(map));
	const line = [];
	(frm.doc.stops || []).forEach((s, i) => {
		if (!s.latitude || !s.longitude) return;
		const ll = [s.latitude, s.longitude];
		line.push(ll);
		const st = (statuses && statuses[s.idx]) || s.status || "Pending";
		const c = HTP_COLORS[st] || HTP_COLORS.Pending;
		L.circle(ll, { radius: s.radius || 150, color: c, weight: 1, fillOpacity: 0.08 }).addTo(g);
		L.marker(ll, { icon: L.divIcon({ className: "", iconSize: [0, 0], html:
			'<span style="position:absolute;left:-13px;top:-13px;width:26px;height:26px;border-radius:50%;background:' + c +
			';color:#fff;border:2px solid #fff;font:700 12px/22px sans-serif;text-align:center;box-shadow:0 1px 4px rgba(0,0,0,.35)">' + (i + 1) + "</span>" }) })
			.bindTooltip((i + 1) + ". " + htp_esc(s.stop_name || s.place || "") + " — " + st).addTo(g);
	});
	if (line.length > 1) L.polyline(line, { color: "#6b7280", weight: 2, dashArray: "6 6" }).addTo(g);
	if (frm.__htp_fit && line.length) {
		if (line.length > 1) map.fitBounds(line, { padding: [40, 40], maxZoom: 16 });
		else map.setView(line[0], 15);
	}
}

function htp_load(frm) {
	return frappe.call({ method: "hipertracker_trip_plan", args: { plan: frm.doc.name } }).then((r) => {
		const d = r.message || {};
		const map = frm.__htp_map, L = window.L;
		if (!map) return;
		if (frm.__htp_route) map.removeLayer(frm.__htp_route);
		const g = (frm.__htp_route = L.layerGroup().addTo(map));
		const pts = (d.points || []).map((p) => [p[0], p[1]]);
		if (pts.length > 1) L.polyline(pts, { color: "#2563eb", weight: 4, opacity: 0.8 }).addTo(g);
		if (d.last) {
			L.circleMarker([d.last.lat, d.last.lon], { radius: 8, color: "#fff", weight: 3, fillColor: "#dc2626", fillOpacity: 1 })
				.bindTooltip(__("Now here ({0})", [String(d.last.time).slice(11, 16)])).addTo(g);
		}
		const statuses = {};
		(d.stops || []).forEach((s) => { statuses[s.idx] = s.status; });
		htp_plan_layer(frm, statuses);
		if (frm.__htp_fit) {
			const all = pts.concat((d.stops || []).map((s) => [s.lat, s.lon]));
			if (all.length > 1) map.fitBounds(all, { padding: [40, 40], maxZoom: 16 });
			frm.__htp_fit = false;
		}
		const wrap = frm.fields_dict.map_html.$wrapper;
		const total = (d.stops || []).length;
		const reached = (d.stops || []).filter((s) => s.status !== "Pending").length;
		wrap.find(".htp-sum").html(!d.device
			? '<span class="text-danger">' + __("This employee has no HiperTracker phone, so the trip can't be followed.") + "</span>"
			: "<b>" + reached + " / " + total + "</b> " + __("stops reached") + " · " + __("planned ~{0} km", [d.planned_km || 0]) +
				" · " + __("travelled {0} km", ["<b>" + (d.actual_km || 0) + "</b>"]) +
				(d.last ? " · " + __("last seen {0}", [d.last.age_minutes < 1 ? __("just now") : Math.round(d.last.age_minutes) + " min ago"]) : ""));
		const pill = (s) => {
			const c = { Pending: "gray", Reached: "orange", Left: "green", Skipped: "gray" }[s] || "gray";
			return '<span class="indicator-pill ' + c + '">' + htp_esc(__(s === "Left" ? "Done" : s)) + "</span>";
		};
		const rows = (d.stops || []).map((s) => "<tr><td><b>" + s.idx + "</b></td><td><b>" + htp_esc(s.name) + "</b>" +
			(s.task ? '<div class="text-muted small">' + htp_esc(s.task) + "</div>" : "") + "</td><td>" + pill(s.status) +
			(s.out_of_order ? ' <span class="text-warning small">' + __("out of order") + "</span>" : "") + "</td><td>" +
			(s.planned || "") + "</td><td>" + (s.arrived ? s.arrived +
				(s.planned && s.late > 10 ? ' <span class="text-danger small">' + __("{0} min late", [s.late]) + "</span>" : "") : "—") +
			"</td><td>" + (s.left || "—") + "</td><td>" + (s.left ? s.minutes + " min" : "") + "</td></tr>").join("");
		wrap.find(".htp-tab").html(rows ? '<table class="table table-sm" style="font-size:13px"><thead><tr><th>#</th><th>' + __("Stop") +
			"</th><th>" + __("Status") + "</th><th>" + __("Planned") + "</th><th>" + __("Reached") + "</th><th>" + __("Left") +
			"</th><th>" + __("Time there") + "</th></tr></thead><tbody>" + rows + "</tbody></table>" : "");
		// keep the header in step without marking the form changed
		if (d.status && d.status !== frm.doc.status && !frm.is_dirty()) frm.reload_doc();
	});
}

function htp_leaflet() {
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
