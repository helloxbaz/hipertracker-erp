# Copyright (c) 2026, Hipersign and contributors
# For license information, please see license.txt

from hipertracker.travel_reports import run


def execute(filters=None):
	return run(filters, "stops")
