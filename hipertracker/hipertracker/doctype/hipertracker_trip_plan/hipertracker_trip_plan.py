# Copyright (c) 2026, Hipersign and contributors
# For license information, please see license.txt

import frappe
import frappe.integrations.utils
from frappe.model.document import Document
from frappe.utils import flt, formatdate

from hipertracker.api import _km

# what a stop can be, and the fields that give its name / phone / address
VISIT_DOCTYPES = ("Customer", "Lead", "Opportunity", "Supplier", "Prospect", "CRM Lead", "CRM Deal", "CRM Organization")
TITLE = {
	"Customer": ["customer_name"], "Supplier": ["supplier_name"], "Lead": ["company_name", "lead_name"],
	"Opportunity": ["customer_name", "title", "party_name"], "Prospect": ["company_name"],
	"CRM Lead": ["organization", "lead_name"], "CRM Deal": ["organization", "lead_name"],
	"CRM Organization": ["organization_name"],
}
PHONE = ("mobile_no", "contact_mobile", "phone", "contact_phone")
ADDRESS = ("hm_address", "primary_address", "address_display", "customer_address")


def _first(doc, fields):
	return next((str(doc.get(f)) for f in fields if doc.get(f)), "")


class HiperTrackerTripPlan(Document):
	"""Stops an employee should visit in order - customers, leads, deals, suppliers ... (their Location), a saved
	Place, or a point on the map. Each is marked reached / left from the phone (hipertracker.api.position)
	and the form shows planned vs actual (hipertracker.api.trip_plan)."""

	def validate(self):
		if not self.device and self.employee:
			self.device = frappe.db.get_value("HiperTracker Device", {"employee": self.employee, "active": 1}, "name")
		if not self.title:
			self.title = f"{self.employee_name or self.employee or 'Trip'} - {formatdate(self.date)}"
		new = self.is_new()
		for st in self.stops:
			if st.reference_doctype and st.reference_doctype not in VISIT_DOCTYPES:
				frappe.throw(f"Stop {st.idx}: a visit can be a {', '.join(VISIT_DOCTYPES)}.")
			if st.reference_doctype and st.reference_name and (new or st.status == "Pending"):
				self._from_record(st)
			if st.place and not (flt(st.latitude) and flt(st.longitude)):
				g = frappe.db.get_value("HiperTracker Geofence", st.place,
										["geofence_name", "latitude", "longitude", "radius"], as_dict=True)
				if g:
					st.latitude, st.longitude = g.latitude, g.longitude
					st.radius = st.radius or g.radius
					st.stop_name = st.stop_name or g.geofence_name
			st.stop_name = st.stop_name or st.reference_name or st.place or f"Stop {st.idx}"
			st.radius = st.radius or 150
			if not (flt(st.latitude) and flt(st.longitude)):
				frappe.throw(f"Stop {st.idx} ({st.stop_name}) has no location. Pick a customer / lead / deal with a "
							 "Location, or click the map on this plan.")
			if new:
				st.update({"status": "Pending", "arrived_at": None, "left_at": None, "minutes": 0, "out_of_order": 0})
		self._legs_and_fuel()
		done = len([s for s in self.stops if s.status != "Pending"])
		self.progress = f"{done} / {len(self.stops)}"
		if new:
			self.update({"status": "Planned", "started_at": None, "finished_at": None, "actual_km": 0})

	def _legs_and_fuel(self):
		"""Road km and driving minutes from the start (if set) / previous stop to each stop, the totals, and the
		petrol needed (km / mileage) and its cost."""
		start = [flt(self.get("start_latitude")), flt(self.get("start_longitude"))]
		pts = ([start] if all(start) else []) + [[flt(s.latitude), flt(s.longitude)] for s in self.stops]
		legs = []
		if len(pts) > 1:
			base = frappe.db.get_single_value("HiperTracker Settings", "routing_url") or "https://router.project-osrm.org"
			try:
				r = frappe.integrations.utils.make_get_request(
					f"{base.rstrip('/')}/route/v1/driving/" + ";".join(f"{lon},{lat}" for lat, lon in pts[:60]) + "?overview=false")
				if r and r.get("code") == "Ok" and r.get("routes"):
					legs = [[flt(lg.get("distance")) / 1000, flt(lg.get("duration")) / 60] for lg in r["routes"][0].get("legs") or []]
			except Exception:
				legs = []
			if len(legs) != len(pts) - 1:
				# roads run about 25 % longer than straight lines; about 30 km/h
				legs = [[_km(*a, *b) * 1.25, _km(*a, *b) * 1.25 / 30 * 60] for a, b in zip(pts, pts[1:])]
		offset = 0 if all(start) else -1
		for i, st in enumerate(self.stops):
			j = i + offset
			st.leg_km, st.leg_minutes = (round(legs[j][0], 1), round(legs[j][1])) if 0 <= j < len(legs) else (0, 0)
		self.planned_km = round(sum(lg[0] for lg in legs), 1)
		self.planned_minutes = round(sum(lg[1] for lg in legs))
		# the trip's vehicle (else the one assigned to the employee, else the phone's) gives the mileage; the price
		# per litre comes from Settings by the vehicle's fuel type - all set in the ERP, not the app
		if not self.vehicle and self.employee:
			self.vehicle = frappe.db.get_value("Vehicle", {"employee": self.employee}, "name")
		if not self.vehicle and self.device:
			self.vehicle = frappe.db.get_value("HiperTracker Device", self.device, "vehicle")
		if self.status != "Completed" or not flt(self.mileage):
			settings = frappe.get_cached_doc("HiperTracker Settings")
			v = frappe.db.get_value("Vehicle", self.vehicle, ["ht_mileage", "fuel_type"], as_dict=True) if self.vehicle else None
			self.mileage = flt(v and v.ht_mileage) or flt(settings.default_mileage)
			diesel = v and v.fuel_type == "Diesel" and flt(settings.diesel_price)
			self.fuel_price = flt(settings.diesel_price) if diesel else flt(settings.fuel_price)
		self.fuel_litres = round(self.planned_km / flt(self.mileage), 2) if flt(self.mileage) else 0
		self.fuel_cost = round(self.fuel_litres * flt(self.fuel_price)) if self.fuel_litres else 0

	def _from_record(self, st):
		"""Name, phone, address and location from the customer / lead / deal; an Opportunity or CRM Deal without a
		location of its own uses its customer, lead or organization's."""
		r = frappe.get_doc(st.reference_doctype, st.reference_name)
		st.stop_name = _first(r, TITLE.get(st.reference_doctype, [])) or st.reference_name
		st.phone = _first(r, PHONE)
		addr = _first(r, ADDRESS) or ", ".join(str(x) for x in (r.get("city"), r.get("state")) if x)
		st.address = addr.replace("<br>", ", ").replace("\n", " ").strip(", ")
		lat, lon = flt(r.get("ht_latitude")), flt(r.get("ht_longitude"))
		if not (lat and lon):
			alt = []
			if st.reference_doctype == "Opportunity" and r.get("opportunity_from") and r.get("party_name"):
				alt.append((r.opportunity_from, r.party_name))
			if st.reference_doctype == "CRM Deal":
				alt += [("CRM Organization", r.get("organization")), ("CRM Lead", r.get("lead"))]
			for dt, name in alt:
				if name and frappe.db.exists(dt, name):
					v = frappe.db.get_value(dt, name, ["ht_latitude", "ht_longitude"], as_dict=True)
					if v and flt(v.ht_latitude) and flt(v.ht_longitude):
						lat, lon = flt(v.ht_latitude), flt(v.ht_longitude)
						break
		if lat and lon:
			st.latitude, st.longitude = lat, lon
		elif not (flt(st.latitude) and flt(st.longitude)):
			frappe.throw(f"{st.reference_doctype} {st.stop_name} (stop {st.idx}) has no location yet. Open it and set its "
						 "Location (click its map or use 'Use my current location' there), then save this plan again.")
