app_name = "hipertracker"
app_title = "HiperTracker"
app_publisher = "Hipersign"
app_description = "Live GPS tracking of staff and vehicles inside Hipersign ERP, straight from the HiperTracker phone app"
app_email = "hipersignerp@gmail.com"
app_license = "mit"
app_logo_url = "/assets/hipertracker/images/hipertracker-logo.png"

# Shows HiperTracker (with its logo) in the apps switcher
add_to_apps_screen = [
	{
		"name": "hipertracker",
		"logo": "/assets/hipertracker/images/hipertracker-logo.png",
		"title": "HiperTracker",
		"route": "/app/hipertracker",
	}
]

# Install / migrate: creates roles, the live map block, the sidebar and the desktop icon
before_install = "hipertracker.install.before_install"
after_install = "hipertracker.install.after_install"
after_migrate = "hipertracker.install.after_migrate"

# The phone app and the map call these short names (first built as server scripts on Nexus)
override_whitelisted_methods = {
	"hipertracker_live": "hipertracker.api.live",
	"hipertracker_history": "hipertracker.api.history",
	"hipertracker_position": "hipertracker.api.position",
	"hipertracker_mobile_config": "hipertracker.api.mobile_config",
	"hipertracker_checkin": "hipertracker.api.checkin",
	"hipertracker_my_day": "hipertracker.api.my_day",
	"hipertracker_delivery_trip": "hipertracker.api.delivery_trip",
	"hipertracker_attendance_today": "hipertracker.api.attendance_today",
	"hipertracker_trip_plan": "hipertracker.api.trip_plan",
	"hipertracker_route": "hipertracker.api.route",
}

# planned vs actual on the Delivery Trip form
doctype_js = {
	"Delivery Trip": "public/js/delivery_trip.js",
	# the Location map on every record a trip stop can be
	**{dt: "public/js/location_picker.js" for dt in (
		"Customer", "Supplier", "Lead", "Opportunity", "Prospect", "CRM Lead", "CRM Deal", "CRM Organization")},
}

# Alert heads about checked-in phones that stopped reporting; trim old location history
scheduler_events = {
	"cron": {"*/5 * * * *": ["hipertracker.api.offline_watch"]},
	"daily": ["hipertracker.api.cleanup"],
}
