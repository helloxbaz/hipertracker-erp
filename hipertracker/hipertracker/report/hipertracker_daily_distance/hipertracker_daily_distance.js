// Copyright (c) 2026, Hipersign and contributors
// For license information, please see license.txt

frappe.query_reports["HiperTracker Daily Distance"] = {
	filters: [
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "device", label: __("Device"), fieldtype: "Link", options: "HiperTracker Device" },
		{ fieldname: "employee", label: __("Employee"), fieldtype: "Link", options: "Employee" },
	],
};
