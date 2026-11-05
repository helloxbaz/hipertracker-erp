# Copyright (c) 2026, Hipersign and contributors
# For license information, please see license.txt
"""Shared code of the HiperTracker travel reports (Daily Distance, Trips, Stops, Speeding)."""

import frappe
from frappe.utils import cint, date_diff, flt, get_datetime, getdate, now_datetime, today

from hipertracker.api import _km, trips_and_stops

C_DATE = {"fieldname": "date", "label": "Date", "fieldtype": "Date", "width": 100}
C_DEV = {"fieldname": "device", "label": "Device", "fieldtype": "Link", "options": "HiperTracker Device", "width": 120}
C_WHO = {"fieldname": "person", "label": "Person", "fieldtype": "Data", "width": 150}


def _col(fieldname, label, fieldtype="Data", width=80, **kw):
	return {"fieldname": fieldname, "label": label, "fieldtype": fieldtype, "width": width, **kw}


COLUMNS = {
	"daily": [
		C_DATE, C_DEV, C_WHO, _col("distance_km", "Distance (km)", "Float", 110, precision=1),
		_col("moving", "Moving (min)", "Int", 100), _col("stopped", "Stopped (min)", "Int", 105),
		_col("trips", "Trips", "Int", 70), _col("stops", "Stops", "Int", 70), _col("max_speed", "Top Speed", "Int", 90),
		_col("over_speed", "Over Speed", "Int", 90), _col("gps_off", "GPS Off", "Int", 80),
		_col("first", "First", width=70), _col("last", "Last", width=70),
	],
	"trips": [
		C_DATE, C_DEV, C_WHO, _col("start", "Start", width=70), _col("end", "End", width=70),
		_col("minutes", "Minutes", "Int"), _col("distance_km", "Distance (km)", "Float", 110, precision=1),
		_col("avg_speed", "Avg km/h", "Int"), _col("max_speed", "Top km/h", "Int"),
		_col("from_place", "From", width=170), _col("to_place", "To", width=170),
	],
	"stops": [
		C_DATE, C_DEV, C_WHO, _col("start", "From", width=70), _col("end", "Until", width=70),
		_col("minutes", "Minutes", "Int"), _col("place", "Place", width=200), _col("map", "Map"),
	],
	"speeding": [
		C_DATE, C_DEV, C_WHO, _col("start", "From", width=70), _col("end", "Until", width=70),
		_col("max_speed", "Top km/h", "Int", 90), _col("limit", "Limit", "Int", 70),
		_col("place", "Where", width=200), _col("map", "Map"),
	],
}


def _map(lat, lon):
	return f"<a target='_blank' href='https://www.google.com/maps?q={lat},{lon}'>Open</a>"


def run(filters, mode):
	filters = frappe._dict(filters or {})
	fd = getdate(filters.from_date or today())
	td = max(getdate(filters.to_date or fd), fd)
	if date_diff(td, fd) > 62:
		frappe.throw("Please choose at most 62 days.")
	dfilt = {}
	if filters.device:
		dfilt["name"] = filters.device
	if filters.employee:
		dfilt["employee"] = filters.employee
	devices = frappe.get_list("HiperTracker Device", filters=dfilt, order_by="device_label asc", limit_page_length=0,
							  fields=["name", "device_label", "employee", "employee_name", "speed_limit"])
	s = frappe.get_cached_doc("HiperTracker Settings")
	stop_min = max(cint(s.stop_minutes) or 5, 1)
	now = now_datetime()
	fences = frappe.get_all("HiperTracker Geofence", filters={"active": 1},
							fields=["name", "latitude", "longitude", "radius"], limit_page_length=500)

	def where(lat, lon):
		for g in fences:
			if _km(lat, lon, flt(g.latitude), flt(g.longitude)) * 1000 <= (cint(g.radius) or 200):
				return g.name
		return f"{round(lat, 5)}, {round(lon, 5)}"

	hhmm = lambda d: str(d)[11:16]  # noqa: E731
	result = []
	for d in devices:
		who = d.employee_name or d.device_label or d.name
		limit = cint(d.speed_limit) or cint(s.speed_limit)
		byday = {}
		for r in frappe.get_all(
			"HiperTracker Position",
			filters=[["device", "=", d.name], ["device_time", ">=", f"{fd} 00:00:00"], ["device_time", "<=", f"{td} 23:59:59"]],
			fields=["device_time", "latitude", "longitude", "speed", "event", "accuracy", "over_speed"],
			order_by="device_time asc", limit_page_length=0,
		):
			byday.setdefault(str(r.device_time)[:10], []).append(r)
		for day, rows in byday.items():
			pts, spells, gps_off, in_spell = [], [], 0, False
			for r in rows:
				gps_off += r.event == "GPS Off"
				if r.event != "Location" or r.latitude is None or r.longitude is None or (r.accuracy and flt(r.accuracy) > 200):
					continue
				p = [flt(r.latitude), flt(r.longitude), get_datetime(r.device_time), flt(r.speed)]
				pts.append(p)
				if r.over_speed:
					if in_spell:
						sp = spells[-1]
						sp["end"] = p[2]
						if p[3] > sp["max_speed"]:
							sp.update(max_speed=p[3], lat=p[0], lon=p[1])
					else:
						spells.append({"start": p[2], "end": p[2], "max_speed": p[3], "lat": p[0], "lon": p[1]})
				in_spell = bool(r.over_speed)
			if not pts and not gps_off:
				continue
			trips, stops = trips_and_stops(pts, stop_min, now)
			base = {"date": day, "device": d.name, "person": who}
			if mode == "daily":
				result.append({
					**base,
					"distance_km": round(sum(_km(pts[i - 1][0], pts[i - 1][1], pts[i][0], pts[i][1]) for i in range(1, len(pts))), 1),
					"moving": sum(t["minutes"] for t in trips), "stopped": sum(x["minutes"] for x in stops),
					"trips": len(trips), "stops": len(stops), "max_speed": round(max((p[3] for p in pts), default=0)),
					"over_speed": len(spells), "gps_off": gps_off,
					"first": hhmm(pts[0][2]) if pts else "", "last": hhmm(pts[-1][2]) if pts else "",
				})
			elif mode == "trips":
				for t in trips:
					result.append({**base, "start": hhmm(t["start"]), "end": hhmm(t["end"]), "minutes": t["minutes"],
								   "distance_km": t["distance_km"], "avg_speed": t["avg_speed"], "max_speed": t["max_speed"],
								   "from_place": where(*t["from"]), "to_place": where(*t["to"])})
			elif mode == "stops":
				for x in stops:
					result.append({**base, "start": hhmm(x["start"]), "end": "now" if x["ongoing"] else hhmm(x["end"]),
								   "minutes": x["minutes"], "place": where(x["lat"], x["lon"]), "map": _map(x["lat"], x["lon"])})
			else:
				for sp in spells:
					result.append({**base, "start": hhmm(sp["start"]), "end": hhmm(sp["end"]), "max_speed": round(sp["max_speed"]),
								   "limit": limit, "place": where(sp["lat"], sp["lon"]), "map": _map(sp["lat"], sp["lon"])})
	result.sort(key=lambda x: (x["date"], x.get("start") or "", x["person"]))
	return COLUMNS[mode], result
