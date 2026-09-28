// Live filtering for the inventory table.
//
// The page ships every strain; this narrows the rows in place as the controls change, so
// typing never waits on the server. services/inventory.py applies the same rules to the
// first render — keep the two in step:
//   search      every word must appear, case-insensitively, in name, breeder or lineage
//   type, expression, breeder   exact match (the no-breeder option matches an empty one)
//   days        the bucket's bounds, inclusive, read off the <option>'s data-low/high
// The URL follows along (replaceState, not a history entry per keystroke), so a reload or a
// shared link lands on the same rows, and the seed +/- buttons come back to them.
(function () {
  var form = document.querySelector('form[data-inventory-filters]');
  var table = document.querySelector('table[data-inventory]');
  if (!form || !table) return;

  var body = table.tBodies[0];
  var count = document.querySelector('[data-inventory-count]');
  var empty = body.querySelector('[data-inventory-empty]');
  var clears = document.querySelectorAll('[data-inventory-clear]');
  var noBreeder = form.dataset.noBreeder;
  var el = form.elements;
  var controls = [el.q, el.type, el.breeder, el.expression, el.days];

  // Read each row once. Lower-casing up front keeps the per-keystroke loop to plain
  // string comparisons over a flat array.
  var rows = Array.prototype.map.call(body.querySelectorAll('tr[data-search]'), function (tr) {
    return {
      tr: tr,
      text: tr.dataset.search.toLowerCase(),
      type: tr.dataset.type,
      breeder: tr.dataset.breeder,
      expression: tr.dataset.expression,
      days: parseInt(tr.dataset.days, 10),
    };
  });

  function bound(option, key) {
    var v = option ? option.dataset[key] : '';
    return v ? parseInt(v, 10) : null;
  }

  function criteria() {
    var dayOption = el.days.selectedIndex > 0 ? el.days.options[el.days.selectedIndex] : null;
    return {
      terms: el.q.value.toLowerCase().split(/\s+/).filter(Boolean),
      type: el.type.value,
      breeder: el.breeder.value,
      expression: el.expression.value,
      low: bound(dayOption, 'low'),
      high: bound(dayOption, 'high'),
    };
  }

  function keeps(r, c) {
    if (c.type && r.type !== c.type) return false;
    if (c.expression && r.expression !== c.expression) return false;
    if (c.breeder && r.breeder !== (c.breeder === noBreeder ? '' : c.breeder)) return false;
    if (c.low !== null && r.days < c.low) return false;
    if (c.high !== null && r.days > c.high) return false;
    for (var i = 0; i < c.terms.length; i++) {
      if (r.text.indexOf(c.terms[i]) === -1) return false;
    }
    return true;
  }

  function syncUrl() {
    var params = new URLSearchParams();
    controls.forEach(function (c) {
      var v = c.name === 'q' ? c.value.trim() : c.value;
      if (v) params.set(c.name, v);
    });
    var qs = params.toString();
    var url = location.pathname + (qs ? '?' + qs : '');
    if (url !== location.pathname + location.search) history.replaceState(history.state, '', url);
  }

  var lastSummary = null;
  function apply() {
    frame = 0;
    var c = criteria();
    var shown = 0;
    for (var i = 0; i < rows.length; i++) {
      var hide = !keeps(rows[i], c);
      // Only touch rows whose state changes: each write can invalidate layout.
      if (rows[i].tr.hidden !== hide) rows[i].tr.hidden = hide;
      if (!hide) shown++;
    }
    var filtered = controls.some(function (ctl) { return ctl.value.trim() !== ''; });
    if (empty) empty.hidden = shown > 0;
    Array.prototype.forEach.call(clears, function (a) {
      if (a.closest('form') === form) a.hidden = !filtered;
    });
    var summary = shown + (shown === 1 ? ' strain' : ' strains') + (filtered ? ' matching your filter' : '');
    // Rewriting identical text would make the live region re-announce it.
    if (count && summary !== lastSummary) count.textContent = summary;
    lastSummary = summary;
    syncUrl();
  }

  // Coalesce bursts (fast typing, key repeat) into one pass per frame.
  var frame = 0;
  function schedule() {
    if (!frame) frame = requestAnimationFrame(apply);
  }

  function reset() {
    controls.forEach(function (c) { c.value = ''; });
    apply();
    el.q.focus();
  }

  form.addEventListener('input', schedule);
  form.addEventListener('change', schedule);
  form.addEventListener('submit', function (ev) {
    ev.preventDefault();
    apply();
  });
  el.q.addEventListener('keydown', function (ev) {
    if (ev.key === 'Escape' && el.q.value) {
      ev.preventDefault();
      el.q.value = '';
      apply();
    }
  });
  Array.prototype.forEach.call(clears, function (a) {
    a.addEventListener('click', function (ev) {
      ev.preventDefault();
      reset();
    });
  });

  form.classList.add('is-live');
  // A back/forward navigation can restore control values the server did not render with.
  apply();
  window.addEventListener('pageshow', function (ev) { if (ev.persisted) apply(); });
})();
