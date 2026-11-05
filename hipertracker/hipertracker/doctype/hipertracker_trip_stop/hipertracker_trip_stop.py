# Copyright (c) 2026, Hipersign and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class HiperTrackerTripStop(Document):
	"""One stop of a Trip Plan; status / times are set as the phone reaches and leaves it."""
