// HiperTracker live map. root_element is provided by Frappe for Custom HTML Blocks.
(function () {
  const R = root_element;
  const el = (name) => R.querySelector('[data-el="' + name + '"]');

  const COLORS = { online: '#16a34a', offline: '#dc2626', gps_off: '#d97706', off_duty: '#9ca3af', unknown: '#6b7280' };
  const LABELS = { online: 'Online', offline: 'Offline', gps_off: 'GPS Off', off_duty: 'Off duty', unknown: 'No data' };

  let state = { data: null, map: null, markers: {}, selected: null, fitted: false, base: null, sat: null, route: null, routeDate: null, routeSum: '' };

  // stop any timer left from an earlier render of this block
  if (window.__hipertrackerTimer) { clearInterval(window.__hipertrackerTimer); window.__hipertrackerTimer = null; }

  const esc = (s) => frappe.utils.escape_html(s == null ? '' : String(s));
  const ago = (min) => {
    if (min == null) return '—';
    if (min < 1) return 'just now';
    if (min < 60) return Math.round(min) + ' min ago';
    if (min < 1440) return Math.round(min / 60) + ' h ago';
    return Math.round(min / 1440) + ' d ago';
  };
  const place = (d) => d.address || (d.lat != null ? (Number(d.lat).toFixed(5) + ', ' + Number(d.lon).toFixed(5)) : '—');

  function loadLeaflet() {
    // the block lives in a shadow root, so Leaflet's stylesheet has to be added inside it
    if (!R.querySelector('link[data-ht-css]')) {
      const css = document.createElement('link');
      css.rel = 'stylesheet';
      css.href = 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css';
      css.setAttribute('data-ht-css', '1');
      R.insertBefore(css, R.firstChild);
    }
    return new Promise((resolve, reject) => {
      if (window.L && window.L.map) return resolve();
      let s = document.getElementById('ht-leaflet-js');
      if (!s) {
        s = document.createElement('script');
        s.id = 'ht-leaflet-js';
        s.src = 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js';
        document.head.appendChild(s);
      }
      s.addEventListener('load', () => resolve());
      s.addEventListener('error', () => reject(new Error('Map library could not load')));
      const t = setInterval(() => { if (window.L && window.L.map) { clearInterval(t); resolve(); } }, 200);
    });
  }

  function initMap(settings) {
    const L = window.L;
    const map = L.map(el('map'), { zoomControl: true, attributionControl: true }).setView(settings.center, settings.zoom);
    // Google road / hybrid tiles
    state.base = L.tileLayer('https://{s}.google.com/vt/lyrs=m&hl=en&x={x}&y={y}&z={z}', {
      subdomains: ['mt0', 'mt1', 'mt2', 'mt3'], maxZoom: 20, attribution: 'Map data &copy; Google' }).addTo(map);
    state.sat = L.tileLayer('https://{s}.google.com/vt/lyrs=y&hl=en&x={x}&y={y}&z={z}', {
      subdomains: ['mt0', 'mt1', 'mt2', 'mt3'], maxZoom: 20, attribution: 'Imagery &copy; Google' });
    map.zoomControl.setPosition('bottomright');
    map.on('click', () => { if (!state.route) select(null); });
    state.map = map;
    setTimeout(() => map.invalidateSize(), 300);
  }

  // a person / vehicle is just a coloured dot; name and speed show on hover or tap
  function dotHtml(d, selected) {
    const color = COLORS[d.status] || COLORS.unknown;
    return '<span class="ht-dot' + (d.status === 'gps_off' ? ' ht-pulse' : '') + (selected ? ' sel' : '') +
      '" style="background:' + color + '"></span>';
  }

  function tipHtml(d) {
    const color = COLORS[d.status] || COLORS.unknown;
    const sub = d.status === 'gps_off' ? 'GPS switched off'
      : d.status === 'off_duty' ? 'Off duty'
      : d.status === 'online' ? (d.speed || 0) + ' km/h'
      : (d.speed || 0) + ' km/h • ' + ago(d.age_minutes);
    return '<b>' + esc(d.label) + '</b><br><span style="color:' + color + '">' + sub + '</span>';
  }

  function renderMarkers() {
    const L = window.L, map = state.map, devices = state.data.devices;
    const keep = {};
    devices.forEach((d) => {
      if (d.lat == null || d.lon == null) return;
      const key = String(d.identifier);
      keep[key] = true;
      const icon = L.divIcon({ className: 'ht-icon', html: dotHtml(d, state.selected === key), iconSize: [0, 0] });
      let m = state.markers[key];
      if (m) { m.setLatLng([d.lat, d.lon]); m.setIcon(icon); m.setTooltipContent(tipHtml(d)); }
      else {
        m = L.marker([d.lat, d.lon], { icon: icon, riseOnHover: true }).addTo(map);
        m.bindTooltip(tipHtml(d), { direction: 'top', offset: [0, -10] });
        m.on('click', (e) => { L.DomEvent.stopPropagation(e); select(key, true); });
        state.markers[key] = m;
      }
      m.setZIndexOffset(state.selected === key ? 1000 : (d.status === 'gps_off' ? 500 : 0));
    });
    Object.keys(state.markers).forEach((k) => { if (!keep[k]) { map.removeLayer(state.markers[k]); delete state.markers[k]; } });
    if (!state.fitted) {
      const pts = devices.filter((d) => d.lat != null).map((d) => [d.lat, d.lon]);
      if (pts.length > 1) map.fitBounds(pts, { padding: [60, 60], maxZoom: 13 });
      else if (pts.length === 1) map.setView(pts[0], 13);
      state.fitted = true;
    }
  }

  function renderKpis() {
    const ds = state.data.devices;
    const c = { total: ds.length, online: 0, offline: 0, gps_off: 0 };
    let sp = 0, n = 0;
    ds.forEach((d) => {
      if (d.status === 'online') c.online++; else if (d.status === 'gps_off') c.gps_off++; else if (d.status !== 'off_duty') c.offline++;
      if (d.status === 'online' && d.speed > 2) { sp += d.speed; n++; }
    });
    c.avg = n ? Math.round(sp / n) + ' km/h' : '0 km/h';
    Object.keys(c).forEach((k) => { const b = R.querySelector('[data-k="' + k + '"]'); if (b) b.textContent = c[k]; });
  }

  function filtered() {
    const q = (el('search').value || '').toLowerCase().trim();
    const st = el('status').value;
    return state.data.devices.filter((d) => {
      if (st) {
        if (st === 'offline' && !(d.status === 'offline' || d.status === 'unknown')) return false;
        if (st !== 'offline' && d.status !== st) return false;
      }
      if (!q) return true;
      return [d.label, d.employee_name, d.department, d.vehicle, d.address, d.identifier, d.head_name]
        .some((v) => v && String(v).toLowerCase().indexOf(q) >= 0);
    });
  }

  function renderTable() {
    const rows = filtered();
    el('listtitle').textContent = 'All Devices (' + state.data.devices.length + ')';
    if (!rows.length) {
      el('rows').innerHTML = '<tr><td colspan="7" class="ht-muted">' +
        (state.data.devices.length ? 'No devices match the filter.' : 'No devices yet. Open Devices &amp; People, add a device and scan its setup QR with the phone.') + '</td></tr>';
      return;
    }
    el('rows').innerHTML = rows.map((d) => {
      const key = String(d.identifier);
      const person = esc(d.employee_name) || '<span class="ht-muted">No employee set</span>';
      return '<tr class="ht-row' + (state.selected === key ? ' sel' : '') + '" data-key="' + key + '">' +
        '<td><b>' + esc(d.label) + '</b><div class="ht-sub">ID ' + esc(d.identifier) + '</div></td>' +
        '<td>' + person + (d.head_name ? '<div class="ht-sub">Head: ' + esc(d.head_name) + '</div>' : '') + '</td>' +
        '<td><span class="ht-badge ht-b-' + d.status + '">' + LABELS[d.status] + '</span></td>' +
        '<td>' + (d.speed || 0) + ' km/h</td>' +
        '<td class="ht-loc" title="' + esc(place(d)) + '">' + esc(place(d)) + '</td>' +
        '<td>' + ago(d.age_minutes) + '</td>' +
        '<td><span class="ht-link" data-focus="' + key + '">Show on map</span></td></tr>';
    }).join('');
    const miss = state.data.not_in_traccar || [];
    const m = el('missing');
    if (miss.length) {
      m.style.display = '';
      m.innerHTML = 'Waiting for the first location from: ' + miss.map((x) =>
        '<span class="ht-link" data-record="' + esc(x.record) + '">' + esc(x.label) + (x.employee_name ? ' (' + esc(x.employee_name) + ')' : '') + '</span>').join(', ') +
        '. Set up those phones with the QR on their device record (or log in to ERP in the app).';
    } else m.style.display = 'none';
  }

  function renderPanel() {
    const p = el('panel');
    const d = state.data && state.data.devices.find((x) => String(x.identifier) === state.selected);
    if (!d) { p.style.display = 'none'; return; }
    const rows = [];
    const add = (k, v) => { if (v !== null && v !== undefined && v !== '') rows.push('<dt>' + k + '</dt><dd>' + v + '</dd>'); };
    add('Person', esc(d.employee_name) || '<span class="ht-muted">Not set</span>');
    add('Department', esc(d.department));
    add('Vehicle', esc(d.vehicle));
    add('Head', esc(d.head_name));
    add('Phone', d.phone ? '<a href="tel:' + esc(d.phone) + '">' + esc(d.phone) + '</a>' : '');
    add('Speed', (d.speed || 0) + ' km/h');
    add('Location', esc(place(d)));
    add('Last update', esc(d.last_update ? frappe.datetime.str_to_user(d.last_update) : '—') + ' <span class="ht-muted">(' + ago(d.age_minutes) + ')</span>');
    if (d.status === 'gps_off') add('GPS', '<b style="color:' + COLORS.gps_off + '">Switched off on the phone</b>' +
      (d.gps_off_since ? ' <span class="ht-muted">since ' + esc(frappe.datetime.str_to_user(d.gps_off_since)) + '</span>' : ''));
    if (d.employee) add('Duty', (d.on_duty ? '<b style="color:' + COLORS.online + '">Checked in</b>' : 'Checked out') +
      (d.duty_since ? ' <span class="ht-muted">(' + esc(frappe.datetime.str_to_user(d.duty_since)) + ')</span>' : ''));
    if (d.ignition != null) add('Ignition', d.ignition ? '<span class="ht-badge ht-b-online">ON</span>' : '<span class="ht-badge ht-b-unknown">OFF</span>');
    if (d.battery != null) add('Battery', Math.round(d.battery) + '%' + (d.charging ? ' (charging)' : ''));
    if (d.odometer != null) add('Odometer', (Math.round(d.odometer / 100) / 10).toLocaleString() + ' km');
    if (d.alarm) add('Last alarm', esc(d.alarm));
    add('Device ID', esc(d.identifier));
    if (!state.routeDate) state.routeDate = frappe.datetime.get_today();
    p.innerHTML = '<button class="ht-close" data-act="close">&times;</button>' +
      '<h3>' + esc(d.label) + '</h3>' +
      '<span class="ht-badge ht-b-' + d.status + '">' + LABELS[d.status] + '</span>' +
      '<dl>' + rows.join('') + '</dl>' +
      '<div class="ht-btns">' +
      '<button class="btn btn-primary btn-sm" data-record="' + esc(d.record) + '">Open Record</button>' +
      (d.lat != null ? '<a class="btn btn-default btn-sm" target="_blank" rel="noopener" href="https://www.google.com/maps/dir/?api=1&destination=' + d.lat + ',' + d.lon + '">Directions</a>' : '') +
      '</div>' +
      '<div class="ht-route"><b>Route history</b><div class="ht-btns">' +
      '<input type="date" class="form-control input-sm" data-el="rdate" value="' + esc(state.routeDate) + '" style="width:150px">' +
      '<button class="btn btn-default btn-sm" data-act="route">Show route</button>' +
      (state.route ? '<button class="btn btn-default btn-sm" data-act="unroute">Hide</button>' : '') + '</div>' +
      '<div class="ht-muted" data-el="rsum">' + (state.routeSum || '') + '</div></div>';
    p.style.display = '';
  }

  function select(key, fromMap) {
    if (key !== state.selected) clearRoute();
    state.selected = key;
    renderMarkers(); renderTable(); renderPanel();
    if (key && !fromMap) {
      const m = state.markers[key];
      if (m) state.map.setView(m.getLatLng(), Math.max(state.map.getZoom(), 14));
    }
  }

  function showAlert(msg, isErr) {
    const a = el('alert');
    if (!msg) { a.style.display = 'none'; return; }
    a.className = 'ht-alert' + (isErr ? ' ht-alert-err' : '');
    a.innerHTML = msg;
    a.style.display = '';
  }

  // ---- route history (positions stored in ERP) ----
  function clearRoute() {
    if (state.route) { state.map.removeLayer(state.route); state.route = null; }
    state.routeSum = '';
  }

  function showRoute() {
    const d = state.data && state.data.devices.find((x) => String(x.identifier) === state.selected);
    if (!d) return;
    const inp = el('rdate');
    state.routeDate = (inp && inp.value) || frappe.datetime.get_today();
    return frappe.call({ method: 'hipertracker_history', args: { device: d.record, date: state.routeDate } }).then((r) => {
      const data = r.message || {};
      const L = window.L;
      clearRoute();
      const g = L.layerGroup().addTo(state.map);
      const pts = (data.points || []).map((p) => [p[0], p[1]]);
      const dot = (ll, color, tip, ring) => L.circleMarker(ll, ring
        ? { radius: 9, color: color, weight: 3, fillOpacity: 0 }
        : { radius: 6, color: '#fff', weight: 2, fillColor: color, fillOpacity: 1 }).bindTooltip(tip).addTo(g);
      if (pts.length) {
        L.polyline(pts, { color: '#2563eb', weight: 4, opacity: 0.85 }).addTo(g);
        dot(pts[0], '#16a34a', 'Start ' + data.points[0][2]);
        dot(pts[pts.length - 1], '#dc2626', 'Last ' + data.points[data.points.length - 1][2]);
      }
      const extra = [];
      (data.checkins || []).forEach((c) => {
        if (c.lat == null) return;
        extra.push([c.lat, c.lon]);
        dot([c.lat, c.lon], c.log_type === 'IN' ? '#16a34a' : '#6b7280', (c.log_type === 'IN' ? 'Checked in ' : 'Checked out ') + String(c.time).slice(11, 16), true);
      });
      (data.events || []).forEach((e) => {
        if (e.lat == null || e.event === 'GPS On') return;
        dot([e.lat, e.lon], COLORS.gps_off, e.event + ' ' + String(e.time).slice(11, 16), true);
      });
      state.route = g;
      const all = pts.concat(extra);
      if (all.length > 1) state.map.fitBounds(all, { padding: [50, 50], maxZoom: 16 });
      else if (all.length) state.map.setView(all[0], 15);
      const n = pts.length;
      const off = (data.events || []).filter((e) => e.event === 'GPS Off').length;
      state.routeSum = n
        ? esc(frappe.datetime.str_to_user(data.date)) + ': <b>' + data.distance_km + ' km</b>, ' + data.points[0][2] + ' – ' + data.points[n - 1][2] +
          (off ? ' · <b style="color:' + COLORS.gps_off + '">GPS off ' + off + '×</b>' : '')
        : 'No route recorded on ' + esc(frappe.datetime.str_to_user(data.date)) + '.';
      renderPanel();
    });
  }

  function load(sync) {
    return frappe.call({ method: 'hipertracker_live', args: { sync: 0 } }).then((r) => {
      const data = r.message || {};
      state.data = data;
      data.devices = data.devices || [];
      R.querySelectorAll('.ht-mgr').forEach((b) => { b.style.display = data.is_manager ? '' : 'none'; });
      if (!state.map) initMap(data.settings);
      if (data.error) {
        showAlert(esc(data.error) + (data.is_manager ? ' <span class="ht-link" data-act="settings">Open Settings</span>' : ''), true);
      } else {
        const gps = data.devices.filter((d) => d.status === 'gps_off');
        const msgs = [];
        if (gps.length) msgs.push('<b>GPS switched off:</b> ' + gps.map((d) => esc(d.label) + (d.employee_name ? ' (' + esc(d.employee_name) + ')' : '')).join(', '));
        showAlert(msgs.join('<br>'), false);
      }
      renderKpis(); renderMarkers(); renderTable(); renderPanel();
      el('updated').textContent = 'Updated ' + frappe.datetime.now_time().slice(0, 5);
      return data;
    });
  }

  // ---- events ----
  R.addEventListener('click', (e) => {
    if (e.target.matches && e.target.matches('input')) return;
    const t = e.target.closest('[data-act],[data-layer],[data-record],[data-focus],tr.ht-row');
    if (!t) return;
    if (t.dataset.act === 'refresh') return load(false);
    if (t.dataset.act === 'route') return showRoute();
    if (t.dataset.act === 'unroute') { clearRoute(); return renderPanel(); }
    if (t.dataset.act === 'settings') return frappe.set_route('Form', 'HiperTracker Settings');
    if (t.dataset.act === 'close') { clearRoute(); return select(null); }
    if (t.dataset.act === 'fullscreen') {
      R.querySelector('.ht-mapwrap').classList.toggle('ht-full');
      return setTimeout(() => state.map && state.map.invalidateSize(), 200);
    }
    if (t.dataset.layer) {
      R.querySelectorAll('[data-layer]').forEach((b) => b.classList.toggle('on', b === t));
      if (t.dataset.layer === 'sat') { state.map.removeLayer(state.base); state.sat.addTo(state.map); }
      else { state.map.removeLayer(state.sat); state.base.addTo(state.map); }
      return;
    }
    if (t.dataset.record) { e.stopPropagation(); return frappe.set_route('Form', 'HiperTracker Device', t.dataset.record); }
    if (t.dataset.focus) { e.stopPropagation(); return select(t.dataset.focus); }
    if (t.dataset.key) return select(t.dataset.key);
  });
  el('search').addEventListener('input', () => state.data && renderTable());
  R.addEventListener('change', (e) => { if (e.target.dataset && e.target.dataset.el === 'rdate') state.routeDate = e.target.value; });
  el('status').addEventListener('change', () => state.data && renderTable());

  loadLeaflet().then(() => load(false)).then((data) => {
    const every = ((data && data.settings && data.settings.refresh) || 30) * 1000;
    window.__hipertrackerTimer = setInterval(() => {
      if (!R.isConnected) { clearInterval(window.__hipertrackerTimer); window.__hipertrackerTimer = null; return; }
      if (document.visibilityState === 'visible') load(false);
    }, every);
  }).catch((err) => {
    showAlert('Could not load the map: ' + esc(err && err.message ? err.message : err), true);
  });
})();
