# Copyright (c) 2026, Hipersign and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class HiperTrackerGeofence(Document):
	"""A place (circle on the map). Phones entering and leaving it are recorded as HiperTracker Geofence Visits."""
