# Copyright (c) 2026, Hipersign and contributors
# For license information, please see license.txt

import random

import frappe
from frappe.model.document import Document


class HiperTrackerDevice(Document):
	def before_insert(self):
		# named by the identifier, so it has to exist before naming (which runs before validate)
		if not self.traccar_identifier:
			for _ in range(10):
				candidate = str(random.randint(10000000, 99999999))
				if not frappe.db.exists("HiperTracker Device", candidate):
					self.traccar_identifier = candidate
					break

	def validate(self):
		# the identifier must match the phone exactly, so drop stray spaces
		if not self.traccar_identifier:
			self.traccar_identifier = str(random.randint(10000000, 99999999))
		self.traccar_identifier = self.traccar_identifier.strip()
		if not self.device_label:
			self.device_label = self.employee_name or self.traccar_identifier
		# the phone sends this key with every location, so nobody else can post locations for the device
		self.device_key = (self.device_key or "").strip() or frappe.generate_hash(length=20)
