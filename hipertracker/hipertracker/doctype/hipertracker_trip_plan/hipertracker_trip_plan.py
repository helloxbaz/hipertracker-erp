# Copyright (c) 2026, Hipersign and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt, formatdate

from hipertracker.api import _km


class HiperTrackerTripPlan(Document):
	"""Stops an employee should visit in order; each is marked reached / left from the phone's location
	(hipertracker.api.position) and the form shows planned vs actual (hipertracker.api.trip_plan)."""

	def validate(self):
		if not self.device and self.employee:
			self.device = frappe.db.get_value("HiperTracker Device", {"employee": self.employee, "active": 1}, "name")
		if not self.title:
			self.title = f"{self.employee_name or self.employee or 'Trip'} - {formatdate(self.date)}"
		new = self.is_new()
		prev, planned = None, 0.0
		for st in self.stops:
			if st.place and not (flt(st.latitude) and flt(st.longitude)):
				g = frappe.db.get_value("HiperTracker Geofence", st.place,
										["geofence_name", "latitude", "longitude", "radius"], as_dict=True)
				if g:
					st.latitude, st.longitude = g.latitude, g.longitude
					st.radius = st.radius or g.radius
					st.stop_name = st.stop_name or g.geofence_name
			st.stop_name = st.stop_name or st.place or f"Stop {st.idx}"
			st.radius = st.radius or 150
			if not (flt(st.latitude) and flt(st.longitude)):
				frappe.throw(f"Stop {st.idx} ({st.stop_name}) has no location. Pick a Place, or set its latitude and longitude.")
			if new:
				st.update({"status": "Pending", "arrived_at": None, "left_at": None, "minutes": 0, "out_of_order": 0})
			cur = [flt(st.latitude), flt(st.longitude)]
			if prev:
				planned += _km(prev[0], prev[1], cur[0], cur[1])
			prev = cur
		self.planned_km = round(planned * 1.25, 1)  # roads run about 25 % longer than straight lines
		done = len([s for s in self.stops if s.status != "Pending"])
		self.progress = f"{done} / {len(self.stops)}"
		if new:
			self.update({"status": "Planned", "started_at": None, "finished_at": None, "actual_km": 0})
