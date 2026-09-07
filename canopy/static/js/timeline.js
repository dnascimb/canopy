/* Canopy timeline (Gantt) renderer.
 *
 * Usage:  Timeline.render(containerEl, { today, start, end, rows })
 * The payload shape is produced by GET /api/v1/timeline and also inlined by the
 * dashboard/schedule templates so the first paint needs no extra request.
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
    container.innerHTML = '';
    container.classList.add('timeline');
    if (!data.rows || !data.rows.length) {
      container.appendChild(el('div', 'tl-empty', 'No groups have a flower start date yet.'));
      return;
    }

    const today = parse(data.today);
    let t0, t1;
    if (data.start && data.end) {
      t0 = parse(data.start); t1 = parse(data.end);
    } else {
      const starts = data.rows.map((r) => parse(r.start)), ends = data.rows.map((r) => parse(r.end));
      t0 = new Date(Math.min(...starts) - 7 * DAY);
      t1 = new Date(Math.max(...ends) + 7 * DAY);
    }
    const total = (t1 - t0) / DAY;
    const pct = (d) => ((d - t0) / DAY / total * 100);

    const inner = el('div', 'tl-inner');
    container.appendChild(inner);

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

    data.rows.forEach((r) => {
      const row = el('div', 'tl-row');
      const label = el('div', 'tl-label');
      const a = el('a', null, r.label);
      a.href = `/groups/${r.id}`;
      a.title = r.label;
      label.appendChild(a);
      row.appendChild(label);

      const track = el('div', 'tl-track');
      boundaries.forEach((p) => {
        const g = el('div', 'tl-gridline');
        g.style.left = p + '%';
        track.appendChild(g);
      });

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
      const text = r.strains.length && r.strains.length <= 2 ? r.strains.join(', ')
                 : r.strains.length ? `${r.strains.length} plants` : '—';
      bar.appendChild(el('span', 'txt', text));
      bar.appendChild(el('span', 'days', `${r.days}d`));

      bar.addEventListener('click', () => { window.location.href = `/groups/${r.id}`; });
      bar.addEventListener('mouseenter', (ev) => {
        const dof = r.day_of_flower ? ` · day ${r.day_of_flower}` : '';
        tip.innerHTML = `<strong>${escape(r.label)}</strong>` +
          `${fmt(s)} → ${fmt(e)} (${r.days} days)${dof}<br>` +
          (r.space ? `${escape(r.space)}<br>` : '') +
          `<span class="tip-strains">${escape(r.strains.join(', ') || 'no living plants')}</span>`;
        tip.style.display = 'block';
        position(ev);
      });
      bar.addEventListener('mousemove', position);
      bar.addEventListener('mouseleave', () => { tip.style.display = 'none'; });
      track.appendChild(bar);
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
