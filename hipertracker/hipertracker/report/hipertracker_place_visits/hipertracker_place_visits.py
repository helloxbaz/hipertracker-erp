# Copyright (c) 2026, Hipersign and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import getdate, now_datetime, time_diff_in_seconds, today


def execute(filters=None):
	"""Who went to which place, how often and for how long (or every visit with 'Show every visit')."""
	filters = frappe._dict(filters or {})
	fd = getdate(filters.from_date or today())
	td = getdate(filters.to_date or fd)
	f = [["entered_at", ">=", f"{fd} 00:00:00"], ["entered_at", "<=", f"{td} 23:59:59"]]
	for key in ("geofence", "device", "employee"):
		if filters.get(key):
			f.append([key, "=", filters.get(key)])
	visits = frappe.get_list("HiperTracker Geofence Visit", filters=f, order_by="entered_at asc", limit_page_length=0,
							 fields=["geofence", "device", "device_label", "employee", "entered_at", "exited_at", "minutes", "inside"])
	emps = list({v.employee for v in visits if v.employee})
	names = dict(frappe.get_all("Employee", filters={"name": ["in", emps]}, fields=["name", "employee_name"], as_list=True)) if emps else {}
	now = now_datetime()

	def minutes(v):
		return int(max(time_diff_in_seconds(now, v.entered_at), 0) // 60) if v.inside else (v.minutes or 0)

	cols = [
		{"fieldname": "geofence", "label": "Place", "fieldtype": "Link", "options": "HiperTracker Geofence", "width": 180},
		{"fieldname": "device", "label": "Device", "fieldtype": "Link", "options": "HiperTracker Device", "width": 120},
		{"fieldname": "person", "label": "Person", "fieldtype": "Data", "width": 150},
	]
	if filters.detail:
		cols += [
			{"fieldname": "entered", "label": "Entered", "fieldtype": "Datetime", "width": 160},
			{"fieldname": "left", "label": "Left", "fieldtype": "Datetime", "width": 160},
			{"fieldname": "minutes", "label": "Minutes", "fieldtype": "Int", "width": 90},
		]
		return cols, [{"geofence": v.geofence, "device": v.device, "person": names.get(v.employee) or v.device_label,
					   "entered": v.entered_at, "left": v.exited_at, "minutes": minutes(v)} for v in visits]
	cols += [
		{"fieldname": "visits", "label": "Visits", "fieldtype": "Int", "width": 80},
		{"fieldname": "minutes", "label": "Total Minutes", "fieldtype": "Int", "width": 110},
		{"fieldname": "first", "label": "First Visit", "fieldtype": "Datetime", "width": 160},
		{"fieldname": "last", "label": "Last Visit", "fieldtype": "Datetime", "width": 160},
		{"fieldname": "inside", "label": "There Now", "fieldtype": "Check", "width": 90},
	]
	groups = {}
	for v in visits:
		g = groups.setdefault((v.geofence, v.device), {
			"geofence": v.geofence, "device": v.device, "person": names.get(v.employee) or v.device_label,
			"visits": 0, "minutes": 0, "first": v.entered_at, "last": v.entered_at, "inside": 0})
		g["visits"] += 1
		g["minutes"] += minutes(v)
		g["last"] = v.entered_at
		g["inside"] = g["inside"] or (1 if v.inside else 0)
	return cols, list(groups.values())
