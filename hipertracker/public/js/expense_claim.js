// HiperTracker: pick a Trip on an expense line and its petrol (km / mileage x price) fills in.
frappe.ui.form.on("Expense Claim Detail", {
	ht_trip_plan(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.ht_trip_plan) return;
		frappe.call({ method: "hipertracker_trip_fuel", args: { plan: row.ht_trip_plan } }).then((r) => {
			const f = r.message || {};
			if (f.claimed_in && f.claimed_in !== frm.doc.name) {
				frappe.msgprint(__("The petrol for this trip is already claimed in {0}.", [f.claimed_in]));
			}
			if (!f.amount) {
				frappe.msgprint(__("This trip has no petrol estimate yet: set the vehicle mileage on the trip plan (or the phone) first."));
				return;
			}
			if (f.expense_type) frappe.model.set_value(cdt, cdn, "expense_type", f.expense_type);
			frappe.model.set_value(cdt, cdn, "expense_date", f.date);
			frappe.model.set_value(cdt, cdn, "amount", f.amount);
			frappe.model.set_value(cdt, cdn, "sanctioned_amount", f.amount);
			frappe.model.set_value(cdt, cdn, "description", f.description);
		});
	},
});
