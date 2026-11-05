# Copyright (c) 2026, Hipersign and contributors
# For license information, please see license.txt
"""HiperTracker: phones send their locations straight to this ERP (no Traccar server).

- position(): the phone app posts each location / GPS on-off event here (same simple form POST
  Traccar's OsmAnd port accepts), with its device key in the URL. Stored as HiperTracker Position and
  kept as the latest state on the HiperTracker Device.
- live(): latest state of every device, for the maps.
- history(): one day's route of a device.
- Heads are alerted (ERP notification + email) when GPS is switched off and stays off, and when a
  checked-in phone stops reporting.
"""

import frappe
from frappe.utils import (
	add_days,
	add_to_date,
	cint,
	convert_utc_to_system_timezone,
	flt,
	format_datetime,
	get_datetime,
	get_url,
	get_url_to_form,
	getdate,
	now_datetime,
	time_diff_in_seconds,
	today,
)

STATUS_LABELS = {"online": "Online", "offline": "Offline", "gps_off": "GPS Off", "off_duty": "Off Duty", "unknown": "No Data"}
STATUS_RANK = {"gps_off": 0, "online": 1, "offline": 2, "off_duty": 3, "unknown": 4}
DEVICE_FIELDS = [
	"name", "traccar_identifier", "device_label", "tracks", "active", "employee", "employee_name", "department",
	"vehicle", "head_name", "phone", "on_duty", "duty_since", "last_update", "last_latitude", "last_longitude",
	"last_speed", "last_course", "last_accuracy", "last_battery", "last_address", "location_enabled",
	"gps_off_since", "last_status",
]


def _is_manager():
	roles = frappe.get_roles()
	return frappe.session.user == "Administrator" or "System Manager" in roles or "HiperTracker Manager" in roles


def _settings():
	s = frappe.get_cached_doc("HiperTracker Settings")
	return s, {
		"center": [flt(s.map_center_lat) or 10.55, flt(s.map_center_lon) or 76.3],
		"zoom": cint(s.map_zoom) or 8,
		"refresh": max(cint(s.refresh_seconds) or 30, 10),
		"stale_minutes": max(cint(s.stale_minutes) or 15, 1),
		"traccar_url": "",
		"duty_mode": cint(s.duty_mode) if s.duty_mode is not None else 1,
		"source": "erp",
	}


# ---------------------------------------------------------------------------------------------
# Map data
# ---------------------------------------------------------------------------------------------


@frappe.whitelist()
def live(sync=0):
	"""Active devices with their latest location (only devices the user can read)."""
	frappe.has_permission("HiperTracker Device", "read", throw=True)
	is_manager = _is_manager()
	_, settings = _settings()
	links = frappe.get_list("HiperTracker Device", fields=DEVICE_FIELDS, filters={"active": 1}, limit_page_length=0)
	now = now_datetime()
	out, no_data = [], []
	for l in links:
		last_dt = get_datetime(l.last_update) if l.last_update else None
		age_min = time_diff_in_seconds(now, last_dt) / 60.0 if last_dt else None
		gps_off = l.location_enabled is not None and not cint(l.location_enabled)
		if last_dt is None:
			status = "unknown"
		elif gps_off:
			status = "gps_off"
		elif age_min > settings["stale_minutes"]:
			status = "offline"
		else:
			status = "online"
		# employees who haven't checked in (or have checked out) aren't expected to be tracked
		if settings["duty_mode"] and l.employee and not l.on_duty:
			status = "off_duty"
		if last_dt is None and status != "off_duty":
			no_data.append({"record": l.name, "label": l.device_label, "identifier": l.traccar_identifier,
							"employee_name": l.employee_name})
		has_pos = l.last_latitude is not None and l.last_longitude is not None and not (
			flt(l.last_latitude) == 0 and flt(l.last_longitude) == 0)
		out.append({
			"traccar_id": None, "identifier": l.traccar_identifier, "traccar_name": None,
			"label": l.device_label or l.employee_name or l.traccar_identifier, "record": l.name, "mapped": 1,
			"tracks": l.tracks or "Person", "employee": l.employee, "employee_name": l.employee_name,
			"department": l.department, "vehicle": l.vehicle, "head_name": l.head_name, "phone": l.phone,
			"status": status, "last_update": str(last_dt) if last_dt else None,
			"age_minutes": round(age_min, 1) if age_min is not None else None,
			"lat": flt(l.last_latitude) if has_pos else None, "lon": flt(l.last_longitude) if has_pos else None,
			"speed": flt(l.last_speed) if status == "online" else 0, "course": l.last_course,
			"address": l.last_address, "battery": l.last_battery, "accuracy": l.last_accuracy,
			"location_enabled": 0 if gps_off else 1,
			"gps_off_since": str(l.gps_off_since) if l.gps_off_since else None,
			"on_duty": 1 if l.on_duty else 0, "duty_since": str(l.duty_since) if l.duty_since else None,
		})
		# keep the list view's Status column right as phones go quiet
		if is_manager and STATUS_LABELS[status] != l.last_status:
			frappe.db.set_value("HiperTracker Device", l.name, "last_status", STATUS_LABELS[status], update_modified=False)
	# places (geofences) for the map, and which place each device is in right now
	geofences = [
		{"name": f.name, "lat": f.latitude, "lon": f.longitude, "radius": f.radius or 200,
		 "color": f.color or "#0ea5e9", "type": f.place_type}
		for f in frappe.get_all("HiperTracker Geofence", filters={"active": 1},
								fields=["name", "latitude", "longitude", "radius", "color", "place_type"], limit_page_length=500)
	]
	inside = {v.device: {"name": v.geofence, "since": str(v.entered_at)[11:16]}
			  for v in frappe.get_all("HiperTracker Geofence Visit", filters={"inside": 1},
									  fields=["device", "geofence", "entered_at"], limit_page_length=5000)}
	for r in out:
		r["place"] = inside.get(r["record"])
	return {
		"settings": settings, "is_manager": 1 if is_manager else 0,
		"devices": sorted(out, key=lambda r: (STATUS_RANK.get(r["status"], 4), (r["label"] or "").lower())),
		"not_in_traccar": no_data, "geofences": geofences, "unmapped_count": 0, "created": 0, "error": None,
	}


@frappe.whitelist()
def history(device, date=None):
	"""The route a phone reported on one day, plus the employee's check ins / outs."""
	if not frappe.get_list("HiperTracker Device", filters={"name": device}, pluck="name"):
		frappe.throw("You do not have access to this device.", frappe.PermissionError)
	return _route(device, date)


def _route(device, date=None):
	day = getdate(date or today())
	start, end = get_datetime(f"{day} 00:00:00"), get_datetime(f"{day} 23:59:59")
	rows = frappe.get_all(
		"HiperTracker Position",
		filters=[["device", "=", device], ["device_time", ">=", start], ["device_time", "<=", end]],
		fields=["device_time", "latitude", "longitude", "speed", "event", "accuracy", "over_speed"],
		order_by="device_time asc",
		limit_page_length=20000,
	)
	points, pts, events, speeding, dist = [], [], [], [], 0.0
	in_spell = False
	for r in rows:
		if r.event != "Location":
			events.append({"time": str(r.device_time), "event": r.event, "lat": r.latitude, "lon": r.longitude})
			continue
		if r.latitude is None or r.longitude is None or (r.accuracy and flt(r.accuracy) > 200):
			continue  # very rough fixes make zig-zags
		lat, lon = round(flt(r.latitude), 6), round(flt(r.longitude), 6)
		if pts:
			dist += _km(pts[-1][0], pts[-1][1], lat, lon)
		points.append([lat, lon, str(r.device_time)[11:16], flt(r.speed)])
		# over-speed spells: consecutive readings over the limit count as one
		if r.over_speed:
			hhmm_ = str(r.device_time)[11:16]
			if in_spell and speeding:
				sp = speeding[-1]
				sp["end"] = hhmm_
				if flt(r.speed) > sp["max_speed"]:
					sp.update(max_speed=round(flt(r.speed)), lat=lat, lon=lon)
			else:
				speeding.append({"start": hhmm_, "end": hhmm_, "max_speed": round(flt(r.speed)), "lat": lat, "lon": lon})
		in_spell = bool(r.over_speed)
		pts.append([lat, lon, get_datetime(r.device_time), flt(r.speed)])
	stop_min = max(cint(frappe.db.get_single_value("HiperTracker Settings", "stop_minutes")) or 5, 1)
	trips, stops = trips_and_stops(pts, stop_min, now_datetime())
	hhmm = lambda d: str(d)[11:16]  # noqa: E731
	for x in trips + stops:
		x["start"], x["end"] = hhmm(x["start"]), hhmm(x["end"])
	checkins = []
	dv = frappe.db.get_value("HiperTracker Device", device, ["employee", "speed_limit"], as_dict=True) or frappe._dict()
	emp = dv.employee
	limit = cint(dv.speed_limit) or cint(frappe.db.get_single_value("HiperTracker Settings", "speed_limit"))
	if emp:
		checkins = [
			{"log_type": c.log_type, "time": str(c.time), "lat": c.latitude, "lon": c.longitude}
			for c in frappe.get_all(
				"Employee Checkin",
				filters=[["employee", "=", emp], ["time", ">=", start], ["time", "<=", end]],
				fields=["log_type", "time", "latitude", "longitude"],
				order_by="time asc",
			)
		]
	return {
		"date": str(day), "points": points, "events": events, "checkins": checkins, "distance_km": round(dist, 1),
		"trips": trips, "stops": stops, "speeding": speeding, "speed_limit": limit,
		"moving_minutes": sum(t["minutes"] for t in trips), "stopped_minutes": sum(st["minutes"] for st in stops),
	}


STOP_RADIUS_KM = 0.15


def trips_and_stops(pts, stop_min, now):
	"""Split one day's points ([lat, lon, datetime, km/h], oldest first) into stops and trips.

	A stop is staying within ~150 m for at least `stop_min` minutes; this also covers the phone going
	quiet while parked, because the app pauses sending when it isn't moving. Trips are the movements
	between stops (shorter than 300 m is GPS jitter, not a trip).
	"""
	n = len(pts)
	if not n:
		return [], []
	stops, a, i = [], 0, 1
	while i <= n:
		if i < n and _km(pts[a][0], pts[a][1], pts[i][0], pts[i][1]) <= STOP_RADIUS_KM:
			i += 1
			continue
		e = i - 1
		ongoing = e == n - 1 and (now - pts[e][2]).total_seconds() < 20 * 60
		secs = ((now if ongoing else pts[e][2]) - pts[a][2]).total_seconds()
		if secs >= stop_min * 60:
			stops.append({"s": a, "e": e, "start": pts[a][2], "end": now if ongoing else pts[e][2],
						  "minutes": int(secs // 60), "lat": pts[a][0], "lon": pts[a][1], "ongoing": ongoing})
		a, i = i, i + 1
	bounds, prev_end = [], 0
	for st in stops:
		bounds.append((prev_end, st["s"]))
		prev_end = st["e"]
	bounds.append((prev_end, n - 1))
	trips = []
	for s, e in bounds:
		if e <= s:
			continue
		dist = sum(_km(pts[k][0], pts[k][1], pts[k + 1][0], pts[k + 1][1]) for k in range(s, e))
		if dist < 0.3:
			continue
		secs = (pts[e][2] - pts[s][2]).total_seconds()
		trips.append({"s": s, "e": e, "start": pts[s][2], "end": pts[e][2], "minutes": int(secs // 60),
					  "distance_km": round(dist, 1), "max_speed": round(max(p[3] or 0 for p in pts[s:e + 1])),
					  "avg_speed": round(dist / (secs / 3600.0)) if secs > 0 else 0,
					  "from": pts[s][:2], "to": pts[e][:2]})
	return trips, stops


def _km(lat1, lon1, lat2, lon2):
	from math import asin, cos, radians, sin, sqrt

	dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
	a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
	return 6371 * 2 * asin(sqrt(a))


# ---------------------------------------------------------------------------------------------
# Locations from the phone app
# ---------------------------------------------------------------------------------------------


def _num(v):
	if v in (None, ""):
		return None
	try:
		return float(v)
	except (TypeError, ValueError):
		return None


def _flag(v):
	if v in (None, ""):
		return None
	return 0 if str(v).lower() in ("false", "0", "no", "off") else 1


@frappe.whitelist(allow_guest=True)
def position(**a):
	"""A location or GPS on/off event from the HiperTracker app.

	Form fields as sent by the app: id, lat, lon, timestamp (unix seconds), speed (knots), bearing,
	altitude, accuracy, batt, charge, alarm, locationEnabled; the device key comes in the URL (?key=).
	Always answers 200, so a phone never gets stuck retrying a point that was rejected.
	"""
	s = frappe.get_cached_doc("HiperTracker Settings")
	fields = ["name", "device_label", "employee", "employee_name", "active", "on_duty", "device_key", "reporting_head",
			  "last_update", "location_enabled", "gps_off_since", "last_alert_at", "last_alert_type",
			  "speed_limit", "last_speed"]
	ident = str(a.get("id") or a.get("deviceid") or "").strip()
	key = str(a.get("key") or "").strip()
	dev = frappe.db.get_value("HiperTracker Device", ident, fields, as_dict=True) if ident else None
	# like Traccar, a phone is known by its ID; a new ID is added so it only needs an Employee set
	ok_ident = 4 <= len(ident) <= 40 and all(c.isalnum() or c in "-_." for c in ident)
	if not dev and ok_ident and a.get("lat") and cint(s.auto_add_devices):
		frappe.get_doc({"doctype": "HiperTracker Device", "traccar_identifier": ident, "device_label": f"Phone {ident}",
						"tracks": "Person", "active": 1}).insert(ignore_permissions=True)
		dev = frappe.db.get_value("HiperTracker Device", ident, fields, as_dict=True)
	if not dev:
		return {"ok": 0, "msg": "unknown device"}
	# the key (sent by phones set up by ERP login or QR) is only required when 'Require device key' is on
	if key and key != (dev.device_key or ""):
		return {"ok": 0, "msg": "wrong device key"}
	if not key and cint(s.require_device_key):
		return {"ok": 0, "msg": "device key required"}
	if not dev.active:
		return {"ok": 0, "msg": "device not active"}
	if not (a.get("lat") or a.get("locationEnabled") or a.get("alarm")):
		return {"ok": 1, "msg": "nothing to record"}  # e.g. the app registering its push token

	now = now_datetime()
	when = now
	ts = _num(a.get("timestamp"))
	if ts:
		try:
			if ts > 100000000000:
				ts = ts / 1000.0
			utc = add_to_date(get_datetime("1970-01-01 00:00:00"), seconds=int(ts))
			when = convert_utc_to_system_timezone(utc).replace(tzinfo=None)
		except Exception:
			when = now
		if time_diff_in_seconds(when, now) > 300:
			when = now

	lat, lon = _num(a.get("lat")), _num(a.get("lon"))
	if lat is not None and lon is not None and (abs(lat) > 90 or abs(lon) > 180 or (lat == 0 and lon == 0)):
		lat = lon = None
	loc_flag = _flag(a.get("locationEnabled"))
	gps_on = 1 if loc_flag is None else loc_flag  # a normal fix means location is on
	alarm = str(a.get("alarm") or "")
	speed = _num(a.get("speed"))
	if speed is not None:
		speed = round(speed * 1.852, 1)  # knots -> km/h
	batt = _num(a.get("batt"))
	if batt is not None and batt <= 1:
		batt *= 100
	# over the speed limit (the device's own limit, else the one in Settings); rough fixes don't count
	limit = cint(dev.speed_limit) or cint(s.speed_limit)
	acc = _num(a.get("accuracy"))
	over = 1 if (limit > 0 and speed and speed > limit and (acc is None or acc <= 50)) else 0
	event = "Location"
	if alarm == "gpsAntennaCut":
		event = "GPS Off Alarm"
	elif loc_flag == 0:
		event = "GPS Off"
	elif loc_flag == 1 and a.get("locationState"):
		event = "GPS On"

	frappe.get_doc({
		"doctype": "HiperTracker Position", "device": dev.name, "device_label": dev.device_label,
		"employee": dev.employee, "device_time": when, "event": event, "on_duty": 1 if dev.on_duty else 0,
		"latitude": lat, "longitude": lon, "accuracy": _num(a.get("accuracy")), "speed": speed,
		"course": _num(a.get("bearing")), "altitude": _num(a.get("altitude")), "battery": batt,
		"charging": _flag(a.get("charge")) or 0, "location_enabled": gps_on,
		"over_speed": over,
	}).insert(ignore_permissions=True)

	# the live state only moves forward (buffered old points just go into the history)
	newest = not dev.last_update or get_datetime(when) >= get_datetime(dev.last_update)
	if newest:
		upd = {"last_update": when, "location_enabled": gps_on}
		if lat is not None:
			upd.update(last_latitude=lat, last_longitude=lon, last_accuracy=_num(a.get("accuracy")) or 0,
					   last_speed=speed or 0, last_course=_num(a.get("bearing")) or 0)
		if batt is not None:
			upd["last_battery"] = batt
		if gps_on:
			upd.update(gps_off_since=None, last_status="Online")
		else:
			upd.update(gps_off_since=dev.gps_off_since or when, last_status="GPS Off")
		if cint(s.duty_mode) and dev.employee and not dev.on_duty:
			upd["last_status"] = "Off Duty"
		if dev.last_alert_type == "offline":
			upd["last_alert_type"] = ""  # a fresh location ends an "offline" alert
		frappe.db.set_value("HiperTracker Device", dev.name, upd, update_modified=False)

	who = dev.employee_name or dev.device_label or dev.name
	if event == "GPS Off Alarm" and newest:
		where = (f'<p>Last known location: <a href="https://www.google.com/maps?q={lat},{lon}">'
				 f"{round(lat, 5)}, {round(lon, 5)}</a></p>") if lat is not None else ""
		_alert(dev, s, "gps_off", f"GPS switched off: {who}",
			   f"<p><b>{who}</b> has switched off location (GPS) on their phone and has not turned it back on"
			   f" after the reminders on the phone.</p><p>Since: {format_datetime(dev.gps_off_since or when)}</p>{where}"
			   f'<p><a href="{get_url_to_form("HiperTracker Device", dev.name)}">Open in HiperTracker</a></p>')
	elif over and newest and cint(s.speed_alert) and flt(dev.last_speed) > limit:
		# two readings in a row over the limit, so a single GPS jump doesn't raise an alert
		where = f'<p>Location: <a href="https://www.google.com/maps?q={lat},{lon}">open in Google Maps</a></p>' if lat is not None else ""
		_alert(dev, s, "speeding", f"Over speed: {who} at {int(speed)} km/h",
			   f"<p><b>{who}</b> is going <b>{int(speed)} km/h</b> (limit {limit} km/h) at {format_datetime(when)}.</p>{where}"
			   f'<p><a href="{get_url_to_form("HiperTracker Device", dev.name)}">Open in HiperTracker</a></p>')
	elif gps_on and newest and dev.last_alert_type == "gps_off" and not dev.location_enabled:
		for u in _head_users(dev):
			_bell(u, dev.name, f"GPS back on: {who}")
		frappe.db.set_value("HiperTracker Device", dev.name, "last_alert_type", "", update_modified=False)
	if newest and lat is not None and (acc is None or acc <= 100):
		_geofences(dev, lat, lon, when, who)
	return {"ok": 1, "msg": None}


def _geofences(dev, lat, lon, when, who):
	"""Record entering / leaving places (HiperTracker Geofence) and alert the head if the place asks for it."""
	fences = frappe.get_all("HiperTracker Geofence", filters={"active": 1},
							fields=["name", "latitude", "longitude", "radius", "alert_on"], limit_page_length=500)
	if not fences:
		return
	inside = {v.geofence: v for v in frappe.get_all("HiperTracker Geofence Visit", filters={"device": dev.name, "inside": 1},
													fields=["name", "geofence", "entered_at"])}
	for f in fences:
		d = _km(lat, lon, flt(f.latitude), flt(f.longitude)) * 1000
		r = cint(f.radius) or 200
		kind = None
		if f.name not in inside and d <= r:
			frappe.get_doc({"doctype": "HiperTracker Geofence Visit", "geofence": f.name, "device": dev.name,
							"device_label": dev.device_label, "employee": dev.employee, "entered_at": when,
							"inside": 1}).insert(ignore_permissions=True)
			kind = "Enter"
		elif f.name in inside and d > r + 50:  # 50 m margin so GPS wobble at the edge isn't many visits
			v = inside[f.name]
			frappe.db.set_value("HiperTracker Geofence Visit", v.name, {
				"exited_at": when, "inside": 0,
				"minutes": int(max(time_diff_in_seconds(when, v.entered_at), 0) // 60)}, update_modified=False)
			kind = "Exit"
		if kind and kind in (f.alert_on or ""):
			subject = f"{who} {'arrived at' if kind == 'Enter' else 'left'} {f.name}"
			body = (f"<p><b>{subject}</b> at {format_datetime(when)}.</p>"
					f'<p><a href="{get_url_to_form("HiperTracker Device", dev.name)}">Open in HiperTracker</a></p>')
			for u in _head_users(dev):
				_bell(u, dev.name, subject, body)
				email = frappe.db.get_value("User", u, "email")
				if email:
					frappe.sendmail(recipients=[email], subject=subject, message=body)


def _head_users(dev):
	if dev.reporting_head:
		return [dev.reporting_head]
	if dev.employee:
		boss = frappe.db.get_value("Employee", dev.employee, "reports_to")
		user = frappe.db.get_value("Employee", boss, "user_id") if boss else None
		if user:
			return [user]
	return []


def _bell(user, device, subject, body=None):
	try:
		frappe.get_doc({"doctype": "Notification Log", "for_user": user, "type": "Alert",
						"document_type": "HiperTracker Device", "document_name": device,
						"subject": subject, "email_content": body}).insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(title="HiperTracker: could not notify " + user)


def _alert(dev, s, kind, subject, body, extra=None):
	"""ERP notification + email to the head; repeated at most every 'Repeat Alerts Every' minutes."""
	now = now_datetime()
	repeat = max(cint(s.alert_repeat_minutes) or 30, 5)
	if dev.last_alert_type == kind and dev.last_alert_at and time_diff_in_seconds(now, dev.last_alert_at) < repeat * 60:
		return
	for u in _head_users(dev):
		_bell(u, dev.name, subject, body)
		email = frappe.db.get_value("User", u, "email")
		if email:
			frappe.sendmail(recipients=[email], subject=subject, message=body)
	frappe.db.set_value("HiperTracker Device", dev.name,
						{"last_alert_at": now, "last_alert_type": kind, **(extra or {})}, update_modified=False)


# ---------------------------------------------------------------------------------------------
# Scheduled jobs (hooks.py)
# ---------------------------------------------------------------------------------------------


def offline_watch():
	"""Every 5 minutes: tell the head when a checked-in phone has stopped sending locations."""
	s = frappe.get_single("HiperTracker Settings")
	if not cint(s.alert_offline):
		return
	stale = max(cint(s.stale_minutes) or 15, 5)
	duty_mode = cint(s.duty_mode)
	now = now_datetime()
	filters = {"active": 1}
	if duty_mode:
		filters["on_duty"] = 1
	for d in frappe.get_all("HiperTracker Device", filters=filters, fields=[
		"name", "device_label", "employee", "employee_name", "reporting_head", "last_update", "duty_since",
		"last_latitude", "last_longitude", "last_alert_at", "last_alert_type"]):
		if duty_mode and not d.employee:
			continue
		since = d.last_update or d.duty_since
		if not since or time_diff_in_seconds(now, since) < stale * 60:
			continue
		who = d.employee_name or d.device_label or d.name
		mins = int(time_diff_in_seconds(now, since) / 60)
		where = (f'<p>Last known location: <a href="https://www.google.com/maps?q={d.last_latitude},{d.last_longitude}">'
				 "open in Google Maps</a></p>") if d.last_latitude is not None else ""
		_alert(d, s, "offline", f"No location from {who} for {mins} minutes",
			   f"<p><b>{who}</b> is checked in, but their phone has not sent a location since {format_datetime(since)}.</p>"
			   "<p>The phone may be switched off, without internet, or the HiperTracker app was stopped.</p>"
			   f'{where}<p><a href="{get_url_to_form("HiperTracker Device", d.name)}">Open in HiperTracker</a></p>',
			   extra={"last_status": "Offline"})


def cleanup():
	"""Daily: delete locations older than 'Keep Location History (days)'."""
	days = cint(frappe.db.get_single_value("HiperTracker Settings", "keep_days") or 90)
	if days > 0:
		frappe.db.delete("HiperTracker Position", {"device_time": ("<", add_days(now_datetime(), -days))})


# ---------------------------------------------------------------------------------------------
# Phone app: ERP login settings and Check In / Check Out
# (also reachable as /api/method/hipertracker_mobile_config and hipertracker_checkin, see hooks.py)
# ---------------------------------------------------------------------------------------------


def _my_employee():
	user = frappe.session.user
	if not user or user == "Guest":
		frappe.throw("Please log in first.", frappe.AuthenticationError)
	emp = frappe.db.get_value(
		"Employee", {"user_id": user, "status": "Active"}, ["name", "employee_name"], as_dict=True
	)
	if not emp:
		frappe.throw(
			f"Your ERP user {user} is not linked to an active Employee. "
			"Ask HR to set your User ID on your Employee record."
		)
	return emp


def _my_device(emp, create=False):
	devs = frappe.get_all(
		"HiperTracker Device",
		filters={"employee": emp.name},
		fields=["name", "traccar_identifier", "device_label", "active", "on_duty", "duty_since"],
		order_by="active desc, modified desc",
		limit=1,
	)
	if devs or not create:
		return devs[0] if devs else None
	doc = frappe.get_doc(
		{
			"doctype": "HiperTracker Device",
			"device_label": emp.employee_name,
			"tracks": "Person",
			"active": 1,
			"employee": emp.name,
		}
	).insert(ignore_permissions=True)
	return frappe._dict(
		name=doc.name,
		traccar_identifier=doc.traccar_identifier,
		device_label=doc.device_label,
		active=1,
		on_duty=0,
		duty_since=None,
	)


def _last_log(emp):
	last = frappe.get_all(
		"Employee Checkin",
		filters={"employee": emp.name},
		fields=["name", "log_type", "time"],
		order_by="time desc",
		limit=1,
	)
	return last[0] if last else None


@frappe.whitelist()
def mobile_config():
	"""Settings for the logged-in worker's phone; creates their HiperTracker Device if needed."""
	emp = _my_employee()
	s = frappe.get_cached_doc("HiperTracker Settings")
	dev = _my_device(emp, create=True)
	key = frappe.db.get_value("HiperTracker Device", dev.name, "device_key")
	if not key:
		key = frappe.generate_hash(length=20)
		frappe.db.set_value("HiperTracker Device", dev.name, "device_key", key, update_modified=False)
	last = _last_log(emp)
	return {
		"user": frappe.session.user,
		"full_name": frappe.db.get_value("User", frappe.session.user, "full_name"),
		"employee": emp.name,
		"employee_name": emp.employee_name,
		"identifier": dev.traccar_identifier,
		"device_label": dev.device_label,
		"device_key": key,
		# the phone sends its locations straight to this ERP, with its device key
		"report_url": get_url("/api/method/hipertracker_position") + "?key=" + key,
		"interval": cint(s.phone_interval) or 60,
		"distance": cint(s.phone_distance) or 50,
		"duty_mode": cint(s.duty_mode) if s.duty_mode is not None else 1,
		"require_location": cint(s.require_location_checkin) if s.require_location_checkin is not None else 1,
		"alarm_interval": max(cint(s.alarm_interval) or 30, 10),
		"escalate_after": max(cint(s.escalate_after), 0) if s.escalate_after is not None else 1,
		"on_duty": 1 if (last and last.log_type == "IN") else 0,
		"last_log_time": str(last.time) if last else None,
	}


@frappe.whitelist(methods=["POST"])
def checkin(log_type, latitude=None, longitude=None, accuracy=None):
	"""Check In (IN) or Check Out (OUT): saves an Employee Checkin with the phone's location."""
	log_type = (log_type or "").strip().upper()
	if log_type not in ("IN", "OUT"):
		frappe.throw("log_type must be IN or OUT")
	emp = _my_employee()
	s = frappe.get_cached_doc("HiperTracker Settings")
	need_location = cint(s.require_location_checkin) if s.require_location_checkin is not None else 1
	has_location = latitude not in (None, "", "null") and longitude not in (None, "", "null")
	if need_location and not has_location:
		frappe.throw(
			f"Your location is needed to check {'in' if log_type == 'IN' else 'out'}. Turn on GPS and try again."
		)
	dev = _my_device(emp)
	last = _last_log(emp)
	if last and last.log_type == log_type:
		return {
			"ok": 1,
			"already": 1,
			"on_duty": 1 if log_type == "IN" else 0,
			"time": str(last.time),
			"checkin": last.name,
			"employee_name": emp.employee_name,
		}
	now = now_datetime()
	data = {
		"doctype": "Employee Checkin",
		"employee": emp.name,
		"log_type": log_type,
		"time": now,
		"device_id": f"HiperTracker {dev.traccar_identifier if dev else ''}".strip(),
	}
	if has_location:
		lat, lon = flt(latitude), flt(longitude)
		data.update(
			{
				"latitude": lat,
				"longitude": lon,
				"geolocation": frappe.as_json(
					{
						"type": "FeatureCollection",
						"features": [
							{"type": "Feature", "properties": {}, "geometry": {"type": "Point", "coordinates": [lon, lat]}}
						],
					}
				),
			}
		)
	doc = frappe.get_doc(data).insert(ignore_permissions=True)
	on_duty = 1 if log_type == "IN" else 0
	if dev:
		frappe.db.set_value(
			"HiperTracker Device", dev.name, {"on_duty": on_duty, "duty_since": now}, update_modified=False
		)
	return {
		"ok": 1,
		"already": 0,
		"on_duty": on_duty,
		"time": str(now),
		"checkin": doc.name,
		"employee_name": emp.employee_name,
	}


@frappe.whitelist()
def my_day(days=14):
	"""For the phone app's My Day tab: my check ins / outs for the last days and today's travel."""
	emp = _my_employee()
	days = min(max(cint(days) or 14, 1), 62)
	start = get_datetime(f"{add_days(today(), -(days - 1))} 00:00:00")
	logs = frappe.get_all(
		"Employee Checkin",
		filters=[["employee", "=", emp.name], ["time", ">=", start]],
		fields=["log_type", "time", "latitude", "longitude"],
		order_by="time desc",
		limit_page_length=500,
	)
	device = frappe.db.get_value("HiperTracker Device", {"employee": emp.name}, "name")
	summary = {"distance_km": 0, "points": 0, "gps_off": 0, "first": None, "last": None, "trips": [], "stops": []}
	if device:
		route = _route(device, today())  # the worker's own phone; no device permission needed
		points = route["points"]
		summary.update(
			distance_km=route["distance_km"],
			points=len(points),
			gps_off=len([e for e in route["events"] if e["event"] == "GPS Off"]),
			first=f"{today()} {points[0][2]}:00" if points else None,
			last=f"{today()} {points[-1][2]}:00" if points else None,
			trips=[{k: t[k] for k in ("start", "end", "minutes", "distance_km", "avg_speed", "max_speed")} for t in route["trips"]],
			stops=[{k: st[k] for k in ("start", "end", "minutes", "ongoing", "lat", "lon")} for st in route["stops"]],
		)
	return {
		"employee": emp.name,
		"employee_name": emp.employee_name,
		"device": device,
		"logs": [{"log_type": l.log_type, "time": str(l.time), "lat": l.latitude, "lon": l.longitude} for l in logs],
		"today": summary,
	}


# ---------------------------------------------------------------------------------------------
# Delivery Trip: planned stops vs the route actually taken
# ---------------------------------------------------------------------------------------------


@frappe.whitelist()
def delivery_trip(trip):
	"""Planned stops (the stop's lat/lng, else a Customer Site place for that customer) against the route the
	vehicle's phone (or the driver's) took since departure, with when each stop was reached and left."""
	if not frappe.get_list("Delivery Trip", filters={"name": trip}, pluck="name"):
		frappe.throw("You do not have access to this Delivery Trip.", frappe.PermissionError)
	doc = frappe.get_doc("Delivery Trip", trip)

	dev, how = None, ""
	if doc.vehicle:
		dev = frappe.db.get_value("HiperTracker Device", {"vehicle": doc.vehicle, "active": 1}, "name")
		how = f"vehicle {doc.vehicle}"
	emp = (frappe.db.get_value("Driver", doc.driver, "employee") if doc.driver else None) or doc.employee
	if not dev and emp:
		dev = frappe.db.get_value("HiperTracker Device", {"employee": emp, "active": 1}, "name")
		how = "driver's phone"

	now = now_datetime()
	start = get_datetime(doc.departure_time) if doc.departure_time else get_datetime(f"{today()} 00:00:00")
	end = min(add_to_date(start, hours=24), now)
	pts = []
	if dev and start <= now:
		for r in frappe.get_all(
			"HiperTracker Position",
			filters=[["device", "=", dev], ["device_time", ">=", start], ["device_time", "<=", end], ["event", "=", "Location"]],
			fields=["device_time", "latitude", "longitude", "accuracy", "speed"], order_by="device_time asc", limit_page_length=20000,
		):
			if r.latitude is None or r.longitude is None or (r.accuracy and flt(r.accuracy) > 200):
				continue
			pts.append([round(flt(r.latitude), 6), round(flt(r.longitude), 6), get_datetime(r.device_time), flt(r.speed)])
	actual_km = sum(_km(pts[i - 1][0], pts[i - 1][1], pts[i][0], pts[i][1]) for i in range(1, len(pts)))

	stops = []
	for s in doc.delivery_stops:
		lat, lon, radius, source = flt(s.lat), flt(s.lng), 150, "stop"
		if not (lat and lon):
			lat = lon = None
			source = ""
			g = frappe.get_all("HiperTracker Geofence", filters={"customer": s.customer, "active": 1},
							   fields=["name", "latitude", "longitude", "radius"], limit_page_length=1) if s.customer else []
			if g:
				lat, lon, radius, source = flt(g[0].latitude), flt(g[0].longitude), cint(g[0].radius) or 150, f"place {g[0].name}"
		addr = (s.customer_address or "").replace("<br>", "\n").replace(",", "\n")
		stops.append({
			"idx": s.idx, "customer": s.customer, "address": ", ".join(x.strip() for x in addr.split("\n") if x.strip()),
			"delivery_note": s.delivery_note, "visited": s.visited, "lat": lat, "lon": lon, "radius": radius, "source": source,
			"eta": str(s.estimated_arrival)[11:16] if s.estimated_arrival else None,
			"arrived": None, "left": None, "minutes": None, "status": "No location" if lat is None else "Pending",
		})

	arrived_at = {}
	for st in stops:
		if st["lat"] is None:
			continue
		near = lambda p, extra=0: _km(p[0], p[1], st["lat"], st["lon"]) * 1000 <= st["radius"] + extra  # noqa: E731
		i = next((k for k, p in enumerate(pts) if near(p)), None)
		if i is None:
			continue
		j = i
		while j + 1 < len(pts) and near(pts[j + 1], 50):
			j += 1
		arrived_at[st["idx"]] = pts[i][2]
		st["arrived"] = str(pts[i][2])[11:16]
		if j + 1 < len(pts):
			st.update(left=str(pts[j][2])[11:16], minutes=int((pts[j][2] - pts[i][2]).total_seconds() // 60), status="Visited")
		else:
			st["status"] = "At stop"
	# visited out of the planned order?
	planned = [st["idx"] for st in stops if st["idx"] in arrived_at]
	for k, idx in enumerate(sorted(arrived_at, key=arrived_at.get)):
		st = next(x for x in stops if x["idx"] == idx)
		st["order"] = k + 1
		if planned[k] != idx:
			st["out_of_order"] = 1

	planned_km, prev = 0.0, (pts[0][:2] if pts else None)
	for st in stops:
		if st["lat"] is None:
			continue
		if prev:
			planned_km += _km(prev[0], prev[1], st["lat"], st["lon"])
		prev = [st["lat"], st["lon"]]

	last = None
	if pts:
		last = {"lat": pts[-1][0], "lon": pts[-1][1], "time": str(pts[-1][2]), "speed": pts[-1][3],
				"age_minutes": round((now - pts[-1][2]).total_seconds() / 60.0, 1)}
	return {
		"trip": doc.name, "status": doc.status, "device": dev, "matched_by": how, "start": str(start), "end": str(end),
		"points": [[p[0], p[1], str(p[2])[11:16], p[3]] for p in pts], "stops": stops, "last": last,
		"planned_km": round(planned_km * 1.25, 1),  # roads are ~25 % longer than straight lines
		"actual_km": round(actual_km, 1),
		"visited": len([s for s in stops if s["status"] in ("Visited", "At stop")]),
		"located": len([s for s in stops if s["lat"] is not None]),
	}


# ---------------------------------------------------------------------------------------------
# Attendance today (workspace block)
# ---------------------------------------------------------------------------------------------


@frappe.whitelist()
def attendance_today():
	"""Today's check ins of the people carrying a HiperTracker phone: first in, last out, late against
	their shift (Shift Assignment, else the employee's default shift) and hours so far."""
	day, now = getdate(today()), now_datetime()
	devs = frappe.get_list("HiperTracker Device", filters={"active": 1, "employee": ["is", "set"]},
						   fields=["name", "employee", "employee_name", "last_status"], limit_page_length=0)
	emps = list({d.employee for d in devs})
	logs, shift_of, shifts, on_leave = {}, {}, {}, set()
	if emps:
		for c in frappe.get_all("Employee Checkin", filters=[["employee", "in", emps], ["time", ">=", f"{day} 00:00:00"]],
								fields=["employee", "log_type", "time"], order_by="time asc", limit_page_length=0):
			logs.setdefault(c.employee, []).append(c)
		for a in frappe.get_all("Shift Assignment", fields=["employee", "shift_type", "end_date"], limit_page_length=0,
								filters=[["employee", "in", emps], ["docstatus", "=", 1], ["status", "=", "Active"],
										 ["start_date", "<=", day]]):
			if not a.end_date or getdate(a.end_date) >= day:
				shift_of[a.employee] = a.shift_type
		for e in frappe.get_all("Employee", filters=[["name", "in", emps]], fields=["name", "default_shift"]):
			if e.name not in shift_of and e.default_shift:
				shift_of[e.name] = e.default_shift
		for st in set(shift_of.values()):
			shifts[st] = frappe.db.get_value("Shift Type", st, ["start_time", "late_entry_grace_period"], as_dict=True)
		on_leave = set(frappe.get_all("Leave Application", pluck="employee", filters=[
			["employee", "in", emps], ["docstatus", "=", 1], ["from_date", "<=", day], ["to_date", ">=", day]]))
	rows = []
	for d in devs:
		first_in = last_out = open_in = None
		worked = 0.0
		for c in logs.get(d.employee, []):
			if c.log_type == "IN":
				first_in = first_in or c.time
				open_in = open_in or c.time
			elif c.log_type == "OUT":
				last_out = c.time
				if open_in:
					worked += time_diff_in_seconds(c.time, open_in)
					open_in = None
		if open_in:
			worked += time_diff_in_seconds(now, open_in)
		status = "On leave" if d.employee in on_leave else "In" if open_in else "Out" if first_in else "Not in"
		late, shift = 0, shift_of.get(d.employee)
		s = shifts.get(shift)
		if first_in and s and s.start_time:
			late = max(int(time_diff_in_seconds(first_in, get_datetime(f"{day} {s.start_time}")) // 60)
					   - cint(s.late_entry_grace_period), 0)
		rows.append({"employee": d.employee, "name": d.employee_name or d.employee, "device": d.name, "status": status,
					 "first_in": str(first_in)[11:16] if first_in else None, "last_out": str(last_out)[11:16] if last_out else None,
					 "hours": round(worked / 3600.0, 1), "late": late, "shift": shift, "gps": d.last_status})
	rank = {"In": 0, "Out": 1, "Not in": 2, "On leave": 3}
	rows.sort(key=lambda r: (rank.get(r["status"], 4), r["name"].lower()))
	count = lambda f: len([r for r in rows if f(r)])  # noqa: E731
	return {"date": str(day), "rows": rows, "total": len(rows), "in": count(lambda r: r["status"] == "In"),
			"came": count(lambda r: r["first_in"]), "late": count(lambda r: r["late"]),
			"not_in": count(lambda r: r["status"] == "Not in"), "leave": count(lambda r: r["status"] == "On leave")}
