// Click-to-sort tables. Mark a table with class="sortable"; a cell's data-v
// overrides its text when comparing, so dates sort by ISO value rather than
// by their "Sep 07" rendering. data-sort-col / data-sort-dir set the default.
(function () {
  var numeric = function (s) { return s !== '' && /^-?\d+(\.\d+)?$/.test(s); };

  function value(row, i) {
    var td = row.children[i];
    if (!td) return '';
    return td.dataset.v !== undefined ? td.dataset.v : td.textContent.trim();
  }

  function compare(x, y) {
    if (numeric(x) && numeric(y)) return parseFloat(x) - parseFloat(y);
    return x.localeCompare(y);
  }

  function sort(table, i, dir) {
    var body = table.tBodies[0];
    var rows = Array.prototype.filter.call(body.rows, function (r) {
      return r.dataset.noSort === undefined;
    });
    var sign = dir === 'desc' ? -1 : 1;
    rows.sort(function (a, b) {
      var x = value(a, i), y = value(b, i);
      // Blanks sink to the bottom either way, so the direction sign must not reach them.
      if (x === '' || y === '') return x === y ? 0 : (x === '' ? 1 : -1);
      return compare(x, y) * sign;
    });
    rows.forEach(function (r) { body.appendChild(r); });
    Array.prototype.forEach.call(table.tHead.rows[0].cells, function (th, n) {
      th.setAttribute('aria-sort', n !== i ? 'none'
        : (dir === 'desc' ? 'descending' : 'ascending'));
    });
  }

  document.querySelectorAll('table.sortable').forEach(function (table) {
    if (!table.tHead || !table.tBodies.length) return;
    Array.prototype.forEach.call(table.tHead.rows[0].cells, function (th, i) {
      if (th.dataset.noSort !== undefined) return;
      th.tabIndex = 0;
      th.setAttribute('role', 'button');
      th.setAttribute('aria-sort', 'none');
      var run = function () {
        sort(table, i, th.getAttribute('aria-sort') === 'descending' ? 'asc' : 'desc');
      };
      th.addEventListener('click', run);
      th.addEventListener('keydown', function (ev) {
        if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); run(); }
      });
    });
    var col = parseInt(table.dataset.sortCol, 10);
    if (!isNaN(col)) sort(table, col, table.dataset.sortDir || 'asc');
  });
})();
