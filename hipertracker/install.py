# Copyright (c) 2026, Hipersign and contributors
# For license information, please see license.txt
"""Sets up HiperTracker on a site: roles, the live map block, sidebar, desktop icon, default settings and device keys.

Runs after install and after every migrate, so changes to the map block in this repo
reach the site with a normal `bench migrate`.
"""

import json
import os

import frappe

APP = "hipertracker"
MODULE = "HiperTracker"
WORKSPACE = "HiperTracker"
BLOCK = "HiperTracker Live Map"
ATTENDANCE_BLOCK = "HiperTracker Attendance Today"
LOGO = "/assets/hipertracker/images/hipertracker-logo.png"
ROLES = ("HiperTracker User", "HiperTracker Manager")
OUR_DOCTYPES = ("HiperTracker Settings", "HiperTracker Device", "HiperTracker Position", "HiperTracker Geofence",
				"HiperTracker Geofence Visit", "HiperTracker Trip Plan", "HiperTracker Trip Stop")
OUR_REPORTS = ("HiperTracker Daily Distance", "HiperTracker Trips", "HiperTracker Stops", "HiperTracker Speeding",
			   "HiperTracker Place Visits")
# made by hand on a site before this app existed; replaced by hipertracker.api.live
OLD_SERVER_SCRIPT = "HiperTracker Live API"
OLD_CLIENT_SCRIPTS = (
	"HiperTracker Device - Live Map",
	"HiperTracker Device - List Map",
	"HiperTracker Device - Phone Setup",
	"HiperTracker Geofence - Map",
	"HiperTracker Delivery Trip - Live Tracking",
	"HiperTracker Trip Plan - Map",
	*(f"HiperTracker {dt} - Location" for dt in (
		"Customer", "Supplier", "Lead", "Opportunity", "Prospect", "CRM Lead", "CRM Deal", "CRM Organization")),
)
OLD_EVENT_SCRIPT = "HiperTracker Device - Sync to Traccar"
# made by hand on Nexus; replaced by hipertracker.api (mobile_config, checkin, position, history, scheduled jobs)
OLD_MOBILE_SCRIPTS = (
	"HiperTracker Mobile Config API",
	"HiperTracker Check In API",
	"HiperTracker Position API",
	"HiperTracker History API",
	"HiperTracker Offline Watch",
	"HiperTracker Cleanup",
	"HiperTracker Device - Key",
	"HiperTracker My Day API",
	"HiperTracker Delivery Trip API",
	"HiperTracker Attendance Today API",
	"HiperTracker Trip Plan API",
	"HiperTracker Route API",
	"HiperTracker My Log API",
	"HiperTracker Visit Places API",
	"HiperTracker Best Order API",
	"HiperTracker Save My Trip API",
	"HiperTracker Trip Plan - Before Save",
	"HiperTracker CRM Lead - Google Location",
	"HiperTracker CRM Deal - Google Location",
)


def before_install():
	"""If HiperTracker was first built by hand on this site, hand those records over to the app."""
	if frappe.db.exists("Module Def", MODULE):
		frappe.db.set_value("Module Def", MODULE, {"app_name": APP, "custom": 0}, update_modified=False)
	for dt in OUR_DOCTYPES:
		if frappe.db.exists("DocType", dt):
			frappe.db.set_value("DocType", dt, {"custom": 0, "module": MODULE}, update_modified=False)
	# reports first made by hand (not standard) make way for the app's own
	for name in OUR_REPORTS:
		if frappe.db.get_value("Report", name, "is_standard") == "No":
			frappe.delete_doc("Report", name, force=True, ignore_permissions=True)
	if frappe.db.exists("Workspace", WORKSPACE):
		frappe.db.set_value("Workspace", WORKSPACE, "modified", "2000-01-01 00:00:00", update_modified=False)


def after_install():
	setup()


def after_migrate():
	setup()


def setup():
	make_roles()
	make_map_block()
	make_location_fields()
	make_sidebar()
	make_desktop_icon()
	set_default_settings()
	give_devices_keys()
	retire_old_server_script()
	frappe.db.commit()


def make_roles():
	for role in ROLES:
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(ignore_permissions=True)


def _read(name, folder="map_block"):
	path = os.path.join(os.path.dirname(__file__), "hipertracker", folder, name)
	with open(path, encoding="utf-8") as f:
		return f.read()


def make_map_block():
	_block(BLOCK, {"html": _read("map.html"), "script": _read("map.js"), "style": _read("map.css")})
	folder = "attendance_block"
	_block(ATTENDANCE_BLOCK, {"html": _read("block.html", folder), "script": _read("block.js", folder),
							  "style": _read("block.css", folder)})


def _block(name, values):
	if frappe.db.exists("Custom HTML Block", name):
		doc = frappe.get_doc("Custom HTML Block", name)
		doc.update(values)
	else:
		doc = frappe.get_doc({"doctype": "Custom HTML Block", "name": name, **values})
	doc.set("roles", [{"role": r} for r in ("System Manager", *ROLES)])
	doc.flags.ignore_permissions = True
	doc.save() if not doc.is_new() else doc.insert()


def make_sidebar():
	"""Frappe v16 sidebar for the workspace (skipped on versions without Workspace Sidebar)."""
	if not frappe.db.exists("DocType", "Workspace Sidebar"):
		return
	# same simple shape as sidebars made in the v16 UI: the map first, so opening the app lands on it
	items = [
		{"label": "Hiper Tracker", "type": "Link", "link_type": "Workspace", "link_to": WORKSPACE, "icon": "map"},
		{"label": "Devices & People", "type": "Link", "link_type": "DocType", "link_to": "HiperTracker Device",
		 "icon": "smartphone"},
		{"label": "Location History", "type": "Link", "link_type": "DocType", "link_to": "HiperTracker Position",
		 "icon": "list"},
		{"label": "Trip Plans", "type": "Link", "link_type": "DocType", "link_to": "HiperTracker Trip Plan",
		 "icon": "route"},
		{"label": "Places (Geofences)", "type": "Link", "link_type": "DocType", "link_to": "HiperTracker Geofence",
		 "icon": "map-pin"},
		{"label": "Place Visits", "type": "Link", "link_type": "DocType", "link_to": "HiperTracker Geofence Visit",
		 "icon": "clock"},
		{"label": "Settings", "type": "Link", "link_type": "DocType", "link_to": "HiperTracker Settings",
		 "icon": "settings"},
	]
	if frappe.db.exists("Workspace Sidebar", WORKSPACE):
		doc = frappe.get_doc("Workspace Sidebar", WORKSPACE)
	else:
		doc = frappe.new_doc("Workspace Sidebar")
		doc.title = WORKSPACE
	doc.update({"title": WORKSPACE, "app": APP})
	doc.set("items", items)
	doc.flags.ignore_permissions = True
	doc.save() if not doc.is_new() else doc.insert()


def make_desktop_icon():
	"""Desktop tile with the HiperTracker logo (Frappe v16)."""
	if not frappe.db.exists("DocType", "Desktop Icon"):
		return
	values = {
		"label": WORKSPACE,
		"icon_type": "Link",
		"link_type": "Workspace Sidebar" if frappe.db.exists("Workspace Sidebar", WORKSPACE) else "External",
		"link_to": WORKSPACE if frappe.db.exists("Workspace Sidebar", WORKSPACE) else None,
		"sidebar": WORKSPACE if frappe.db.exists("Workspace Sidebar", WORKSPACE) else None,
		"link": "/app/hipertracker",
		"logo_url": LOGO,
		"app": APP,
		"bg_color": "blue",
		"hidden": 0,
	}
	name = frappe.db.get_value("Desktop Icon", {"label": WORKSPACE}) or frappe.db.get_value(
		"Desktop Icon", {"app": APP}
	)
	if name:
		doc = frappe.get_doc("Desktop Icon", name)
		doc.update(values)
	else:
		doc = frappe.get_doc({"doctype": "Desktop Icon", **values})
	doc.flags.ignore_permissions = True
	doc.flags.ignore_links = True
	doc.save() if not doc.is_new() else doc.insert()


def set_default_settings():
	s = frappe.get_single("HiperTracker Settings")
	changed = False
	defaults = {
		"traccar_url": "https://gps.hipersignerp.cloud",
		"auth_method": "API Token",
		"map_center_lat": 10.55,
		"map_center_lon": 76.3,
		"map_zoom": 8,
		"refresh_seconds": 30,
		"stale_minutes": 15,
		"phone_report_url": "http://gps.hipersignerp.cloud:5055",
		"app_download_url": "https://github.com/hipersignerp-dev/Hipersign-traccar-client/releases/latest/download/HiperTracker.apk",
		"phone_interval": 60,
		"phone_distance": 50,
		"alarm_interval": 30,
		"keep_days": 90,
		"alert_repeat_minutes": 30,
		"stop_minutes": 5,
	}
	for key, value in defaults.items():
		if not s.get(key):
			s.set(key, value)
			changed = True
	if changed:
		s.flags.ignore_permissions = True
		s.save()


def give_devices_keys():
	"""Every device needs a key before its phone can send locations to the ERP."""
	for name in frappe.get_all("HiperTracker Device", filters={"device_key": ("in", ("", None))}, pluck="name"):
		frappe.db.set_value("HiperTracker Device", name, "device_key", frappe.generate_hash(length=20), update_modified=False)


def retire_old_server_script():
	for name in (OLD_SERVER_SCRIPT, OLD_EVENT_SCRIPT, *OLD_MOBILE_SCRIPTS):
		if frappe.db.exists("Server Script", name):
			frappe.db.set_value("Server Script", name, "disabled", 1)
	# the app ships these as hipertracker_device.js / _list.js
	for name in OLD_CLIENT_SCRIPTS:
		if frappe.db.exists("Client Script", name):
			frappe.db.set_value("Client Script", name, "enabled", 0)


# ---------------------------------------------------------------------------------------------
# Location on customers, leads, deals ... (trip-plan stops take their location from it)
# ---------------------------------------------------------------------------------------------

LOCATION_AFTER = {
	"Customer": "loyalty_program_tier", "Supplier": "payment_terms", "Lead": "blog_subscriber",
	"Opportunity": "competitors", "Prospect": "column_break_16", "CRM Lead": "lead_owner",
	"CRM Deal": "closed_date", "CRM Organization": "address",
}
CRM_DOCTYPES = ("CRM Lead", "CRM Deal", "CRM Organization")


def make_location_fields():
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	fields = {}
	for dt, after in LOCATION_AFTER.items():
		if not frappe.db.exists("DocType", dt):
			continue  # e.g. Frappe CRM not installed
		fields[dt] = [
			{"fieldname": "ht_location_section", "fieldtype": "Section Break", "label": "Location", "insert_after": after},
			{"fieldname": "ht_location_map", "fieldtype": "HTML", "label": "Location Map", "insert_after": "ht_location_section"},
			{"fieldname": "ht_coords_section", "fieldtype": "Section Break", "insert_after": "ht_location_map"},
			{"fieldname": "ht_latitude", "fieldtype": "Float", "label": "Latitude", "precision": "7", "no_copy": 1,
			 "insert_after": "ht_coords_section", "description": "Set by clicking the map above"},
			{"fieldname": "ht_coords_column", "fieldtype": "Column Break", "insert_after": "ht_latitude"},
			{"fieldname": "ht_longitude", "fieldtype": "Float", "label": "Longitude", "precision": "7", "no_copy": 1,
			 "insert_after": "ht_coords_column"},
		]
	create_custom_fields(fields, ignore_validate=True)
	if frappe.db.exists("DocType", "CRM Form Script"):
		script = _read("crm_form_script.js", "location_picker")
		for dt in CRM_DOCTYPES:
			name = f"HiperTracker {dt} Location"
			body = script.replace("__DT__", dt).replace("__CLS__", dt.replace(" ", ""))
			if frappe.db.exists("CRM Form Script", name):
				frappe.db.set_value("CRM Form Script", name, "script", body)
			else:
				frappe.get_doc({"doctype": "CRM Form Script", "name": name, "dt": dt, "view": "Form", "enabled": 1,
								"script": body}).insert(ignore_permissions=True)
			layout = f"{dt}-Side Panel"
			if frappe.db.exists("CRM Fields Layout", layout):
				lay = json.loads(frappe.db.get_value("CRM Fields Layout", layout, "layout") or "[]")
				if "ht_latitude" not in json.dumps(lay):
					section = {"label": "Location", "name": "ht_location_section", "opened": True}
					if lay and "columns" in lay[0]:
						section["columns"] = [{"name": "column_htloc", "fields": ["ht_latitude", "ht_longitude"]}]
					else:
						section["fields"] = ["ht_latitude", "ht_longitude"]
					lay.append(section)
					frappe.db.set_value("CRM Fields Layout", layout, "layout", json.dumps(lay))
