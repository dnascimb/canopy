/* Canopy timeline (Gantt) renderer.
 *
 * Usage:  Timeline.render(containerEl, { today, start, end, rows })
 * The payload shape is produced by GET /api/v1/timeline and also inlined by the
 * dashboard/schedule templates so the first paint needs no extra request.
 *
 * One toggle above the chart: "Full cycle".
 *   off  flower spans only. The default, and byte-for-byte what this drew before.
 *   on   adds the pre-flower span in front of each bar, and brings in units that have
 *        not flipped yet.
 * The toggle only appears when there is pre-flower data to show.
 */
const Timeline = (() => {
  const DAY = 86400000;
  const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];

  const parse = (s) => new Date(s + 'T00:00:00Z');
  const fmt = (d) => `${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()}`;
  const el = (tag, cls, text) => {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  };

  function render(container, data) {
    const any = (data.rows || []).some((r) => r.pre_start);
    draw(container, data, false, any);
  }

  function draw(container, data, full, offer) {
    container.innerHTML = '';
    container.classList.add('timeline');
    if (!data.rows || !data.rows.length) {
      container.appendChild(el('div', 'tl-empty', 'Nothing to show yet.'));
      return;
    }
    const showPre = full;
    const showFlower = true;
    const rowsIn = data.rows.filter((r) => (full ? (r.start || r.pre_start) : r.start));

    const today = parse(data.today);
    let t0, t1;
    const lo = [], hi = [];
    rowsIn.forEach((r) => {
      if (showFlower && r.start) { lo.push(parse(r.start)); hi.push(parse(r.end)); }
      if (showPre && r.pre_start) { lo.push(parse(r.pre_start)); hi.push(r.start ? parse(r.start) : today); }
    });
    if (!full && data.start && data.end) {
      // The default keeps the server's bounds, so it is unchanged by all of this.
      t0 = parse(data.start); t1 = parse(data.end);
    } else if (lo.length) {
      t0 = new Date(Math.min(...lo) - 7 * DAY);
      t1 = new Date(Math.max(...hi) + 7 * DAY);
    } else {
      t0 = parse(data.start || data.today); t1 = parse(data.end || data.today);
    }
    const total = (t1 - t0) / DAY;
    const pct = (d) => ((d - t0) / DAY / total * 100);

    const inner = el('div', 'tl-inner');
    container.appendChild(inner);

    if (offer) {
      const sw = el('div', 'tl-views');
      const b = el('button', 'tl-view' + (full ? ' on' : ''), 'Full cycle');
      b.type = 'button';
      b.setAttribute('aria-pressed', full ? 'true' : 'false');
      b.addEventListener('click', () => draw(container, data, !full, offer));
      sw.appendChild(b);
      inner.appendChild(sw);
    }

    // Month header: one cell per calendar month intersecting the range.
    const months = el('div', 'tl-months');
    let m = new Date(Date.UTC(t0.getUTCFullYear(), t0.getUTCMonth(), 1));
    const boundaries = [];
    let idx = 0;
    while (m < t1) {
      const next = new Date(Date.UTC(m.getUTCFullYear(), m.getUTCMonth() + 1, 1));
      const from = Math.max(m, t0), to = Math.min(next, t1);
      const showYear = idx++ === 0 || m.getUTCMonth() === 0;
      const cell = el('div', 'tl-month', showYear ? `${MONTHS[m.getUTCMonth()]} ${m.getUTCFullYear()}` : MONTHS[m.getUTCMonth()]);
      cell.style.width = (pct(to) - pct(from)) + '%';
      months.appendChild(cell);
      if (m > t0) boundaries.push(pct(m));
      m = next;
    }
    inner.appendChild(months);

    const rows = el('div', 'tl-rows');
    inner.appendChild(rows);

    const tip = el('div', 'tl-tip');
    inner.appendChild(tip);

    rowsIn.forEach((r) => {
      const row = el('div', 'tl-row');
      const label = el('div', 'tl-label');
      const a = el('a', null, r.label);
      a.href = r.href || `/groups/${r.id}`;
      a.title = r.label;
      label.appendChild(a);
      row.appendChild(label);

      const track = el('div', 'tl-track');
      boundaries.forEach((p) => {
        const g = el('div', 'tl-gridline');
        g.style.left = p + '%';
        track.appendChild(g);
      });

      const label_of = (r) => r.strains.length && r.strains.length <= 2 ? r.strains.join(', ')
                            : r.strains.length ? `${r.strains.length} plants` : '—';
      const open = (ev, html) => {
        tip.innerHTML = html;
        tip.style.display = 'block';
        position(ev);
      };
      const wire = (node) => {
        node.addEventListener('click', () => { window.location.href = r.href || `/groups/${r.id}`; });
        node.addEventListener('mousemove', position);
        node.addEventListener('mouseleave', () => { tip.style.display = 'none'; });
      };

      // Pre-flower: alive but not yet flowering. Drawn first so it sits behind.
      if (showPre && r.pre_start) {
        const ps = parse(r.pre_start);
        const pe = r.start ? parse(r.start) : today;   // still going if it has not flipped
        const pre = el('div', 'tl-bar pre');
        if (!r.start) pre.classList.add('open');
        pre.style.left = pct(ps) + '%';
        pre.style.width = Math.max(pct(pe) - pct(ps), 0.6) + '%';
        pre.style.background = r.color;
        const days = Math.round((pe - ps) / DAY);
        pre.addEventListener('mouseenter', (ev) => open(ev,
          `<strong>${escape(r.label)}</strong>` +
          `${fmt(ps)} → ${r.start ? fmt(pe) : 'still'} (${days} days before flower)<br>` +
          (r.space ? `${escape(r.space)}<br>` : '') +
          `<span class="tip-strains">${escape(r.strains.join(', ') || 'no living plants')}</span>`));
        wire(pre);
        track.appendChild(pre);
      }

      if (showFlower && r.start) {
        const s = parse(r.start), e = parse(r.end);
        const bar = el('div', 'tl-bar');
        bar.style.left = pct(s) + '%';
        bar.style.width = Math.max(pct(e) - pct(s), 0.6) + '%';
        bar.style.background = r.color;
        if (today < s) bar.classList.add('future');
        if (today >= e) bar.classList.add('done');

        if (today > s && today < e) {
          const elapsed = el('div', 'elapsed');
          elapsed.style.width = (r.progress * 100) + '%';
          bar.appendChild(elapsed);
        }
        bar.appendChild(el('span', 'txt', label_of(r)));
        bar.appendChild(el('span', 'days', `${r.days}d`));
        bar.addEventListener('mouseenter', (ev) => {
          const dof = r.day_of_flower ? ` · day ${r.day_of_flower}` : '';
          open(ev, `<strong>${escape(r.label)}</strong>` +
            `${fmt(s)} → ${fmt(e)} (${r.days} days)${dof}<br>` +
            (r.space ? `${escape(r.space)}<br>` : '') +
            `<span class="tip-strains">${escape(r.strains.join(', ') || 'no living plants')}</span>`);
        });
        wire(bar);
        track.appendChild(bar);
      }
      row.appendChild(track);
      rows.appendChild(row);
    });

    // Today line spans all rows; sits inside the track column.
    if (today >= t0 && today <= t1) {
      const line = el('div', 'tl-today');
      const labelW = getComputedStyle(container).getPropertyValue('--label-w').trim() || '120px';
      line.style.left = `calc(${labelW} + (100% - ${labelW}) * ${pct(today) / 100})`;
      line.appendChild(el('div', 'tl-today-label', 'today'));
      rows.appendChild(line);
    }

    function position(ev) {
      const rect = inner.getBoundingClientRect();
      let x = ev.clientX - rect.left + 14, y = ev.clientY - rect.top + 14;
      if (x + tip.offsetWidth > rect.width) x = Math.max(0, x - tip.offsetWidth - 28);
      tip.style.left = x + 'px';
      tip.style.top = y + 'px';
    }
  }

  function escape(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }

  function mount(selector) {
    document.querySelectorAll(selector).forEach((node) => {
      const inline = node.querySelector('script[type="application/json"]');
      if (inline) {
        render(node, JSON.parse(inline.textContent));
      } else {
        fetch('/api/v1/timeline').then((r) => r.json()).then((d) => render(node, d));
      }
    });
  }

  return { render, mount };
})();

document.addEventListener('DOMContentLoaded', () => Timeline.mount('[data-timeline]'));
