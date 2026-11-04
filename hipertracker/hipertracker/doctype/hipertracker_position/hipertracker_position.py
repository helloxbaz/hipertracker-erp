# Copyright (c) 2026, Hipersign and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class HiperTrackerPosition(Document):
	"""One location (or GPS on/off event) sent by a phone; written by hipertracker.api.position."""
