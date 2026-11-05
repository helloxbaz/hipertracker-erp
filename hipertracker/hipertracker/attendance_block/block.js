// Custom HTML Block "HiperTracker Attendance Today": today's check ins of the people carrying a HiperTracker phone.
(function () {
  const R = root_element;
  const esc = (s) => frappe.utils.escape_html(s == null ? '' : String(s));
  function load() {
    return frappe.call({ method: 'hipertracker_attendance_today' }).then((r) => {
      const d = r.message || {};
      R.querySelector('.hta-date').textContent = frappe.datetime.str_to_user(d.date);
      const k = (n, label, color) => '<div class="hta-kpi"><b style="color:' + color + '">' + n + '</b><span>' + label + '</span></div>';
      R.querySelector('.hta-kpis').innerHTML =
        k(d.in || 0, 'Checked in now', '#15803d') + k(d.came || 0, 'Came today', 'inherit') +
        k(d.late || 0, 'Late', '#b45309') + k(d.not_in || 0, 'Not checked in', '#b91c1c') + k(d.leave || 0, 'On leave', '#7c3aed');
      const rows = (d.rows || []).map((x) => '<tr><td><a href="/app/employee/' + encodeURIComponent(x.employee) + '">' + esc(x.name) + '</a></td>' +
        '<td><span class="hta-pill hta-' + esc(x.status.split(' ')[0]) + '">' + esc(x.status) + '</span></td>' +
        '<td>' + (x.first_in ? esc(x.first_in) : '—') + (x.late ? ' <span class="hta-late">' + x.late + ' min late</span>' : '') + '</td>' +
        '<td>' + (x.last_out ? esc(x.last_out) : '—') + '</td><td>' + (x.hours ? x.hours + ' h' : '') + '</td>' +
        '<td class="text-muted">' + esc(x.shift || '') + '</td></tr>').join('');
      R.querySelector('.hta-list').innerHTML = rows
        ? '<table><thead><tr><th>Person</th><th>Status</th><th>In</th><th>Out</th><th>Hours</th><th>Shift</th></tr></thead><tbody>' + rows + '</tbody></table>'
        : '<div class="text-muted">No people with a HiperTracker phone yet.</div>';
    });
  }
  load();
  clearInterval(window.__htaTimer);
  window.__htaTimer = setInterval(() => {
    if (!document.body.contains(R.host || R)) return clearInterval(window.__htaTimer);
    if (document.visibilityState === 'visible') load();
  }, 120000);
})();
