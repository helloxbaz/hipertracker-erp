// HiperTracker location actions for __DT__ in the Frappe CRM screens (CRM Form Script).
class __CLS__ {
	onLoad() {
		if (this.doc.__newDocument) return
		const save = (lat, lon) =>
			call("frappe.client.set_value", {
				doctype: "__DT__",
				name: this.doc.name,
				fieldname: { ht_latitude: Number(Number(lat).toFixed(7)), ht_longitude: Number(Number(lon).toFixed(7)) },
			}).then(() => {
				this.doc.ht_latitude = Number(Number(lat).toFixed(7))
				this.doc.ht_longitude = Number(Number(lon).toFixed(7))
				toast.success(__("Location saved"))
			})
		this.actions.push({
			label: __("Set location to where I am"),
			onClick: () => {
				if (!navigator.geolocation) return toast.error(__("This browser can't give a location"))
				navigator.geolocation.getCurrentPosition(
					(p) => save(p.coords.latitude, p.coords.longitude),
					() => toast.error(__("Could not get your location. Allow location for this site.")),
					{ enableHighAccuracy: true, timeout: 15000 },
				)
			},
		})
		this.actions.push({
			label: __("Set location from Google Maps link"),
			onClick: () => {
				const v = window.prompt(__("Paste a Google Maps link, or 'lat, lon'"))
				if (!v) return
				const t = decodeURIComponent(v)
				const m = t.match(/@(-?\d+\.\d+),(-?\d+\.\d+)/) || t.match(/[?&](?:q|query|ll|destination)=(-?\d+\.\d+),\s*(-?\d+\.\d+)/) ||
					t.match(/!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)/) || t.match(/^\s*(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)\s*$/)
				if (!m) return toast.error(__("No location found in that link. Open short links first and copy the full address."))
				save(m[1], m[2])
			},
		})
		this.actions.push({
			label: __("Open location in Google Maps"),
			onClick: () => {
				if (!this.doc.ht_latitude) return toast.error(__("No location set yet"))
				window.open("https://www.google.com/maps?q=" + this.doc.ht_latitude + "," + this.doc.ht_longitude, "_blank")
			},
		})
	}
}
