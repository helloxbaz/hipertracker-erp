# Copyright (c) 2026, Hipersign and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class HiperTrackerGeofenceVisit(Document):
	"""One stay of a device inside a place; written by hipertracker.api.position."""
