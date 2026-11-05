# Copyright (c) 2026, Hipersign and contributors
# For license information, please see license.txt
"""Sets up HiperTracker on a site: roles, the live map block, sidebar, desktop icon, default settings and device keys.

Runs after install and after every migrate, so changes to the map block in this repo
reach the site with a normal `bench migrate`.
"""

import os

import frappe

APP = "hipertracker"
MODULE = "HiperTracker"
WORKSPACE = "HiperTracker"
BLOCK = "HiperTracker Live Map"
LOGO = "/assets/hipertracker/images/hipertracker-logo.png"
ROLES = ("HiperTracker User", "HiperTracker Manager")
OUR_DOCTYPES = ("HiperTracker Settings", "HiperTracker Device")
# made by hand on a site before this app existed; replaced by hipertracker.api.live
OLD_SERVER_SCRIPT = "HiperTracker Live API"
OLD_CLIENT_SCRIPTS = (
	"HiperTracker Device - Live Map",
	"HiperTracker Device - List Map",
	"HiperTracker Device - Phone Setup",
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
)


def before_install():
	"""If HiperTracker was first built by hand on this site, hand those records over to the app."""
	if frappe.db.exists("Module Def", MODULE):
		frappe.db.set_value("Module Def", MODULE, {"app_name": APP, "custom": 0}, update_modified=False)
	for dt in OUR_DOCTYPES:
		if frappe.db.exists("DocType", dt):
			frappe.db.set_value("DocType", dt, {"custom": 0, "module": MODULE}, update_modified=False)
	if frappe.db.exists("Workspace", WORKSPACE):
		frappe.db.set_value("Workspace", WORKSPACE, "modified", "2000-01-01 00:00:00", update_modified=False)


def after_install():
	setup()


def after_migrate():
	setup()


def setup():
	make_roles()
	make_map_block()
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


def _read(name):
	path = os.path.join(os.path.dirname(__file__), "hipertracker", "map_block", name)
	with open(path, encoding="utf-8") as f:
		return f.read()


def make_map_block():
	values = {
		"html": _read("map.html"),
		"script": _read("map.js"),
		"style": _read("map.css"),
	}
	if frappe.db.exists("Custom HTML Block", BLOCK):
		doc = frappe.get_doc("Custom HTML Block", BLOCK)
		doc.update(values)
	else:
		doc = frappe.get_doc({"doctype": "Custom HTML Block", "name": BLOCK, **values})
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
