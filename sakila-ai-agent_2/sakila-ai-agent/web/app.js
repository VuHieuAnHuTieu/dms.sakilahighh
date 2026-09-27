(function () {
"use strict";
const D = window.SAKILA_DATA, E = window.SakilaEngine(D), SQL = window.SAKILA_SQL || {};
const $ = (s, r = document) => r.querySelector(s);
const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const fmt = (n, d = 0) => Number(n).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
const pct = (x, d = 2) => `${(100 * x).toFixed(d)}%`;
const money = n => "$" + fmt(n, 2);
const title = s => String(s).toLowerCase().replace(/\b\w/g, c => c.toUpperCase());
const cssv = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const state = { customer: 42, exploration: false, inStock: true, heat: "prob", rankBy: "transitions", fromCat: "Action", journeyCustomer: 42 };
try { const s = JSON.parse(localStorage.getItem("sakila-ui") || "{}"); Object.assign(state, s); } catch (e) {}
const save = () => { try { localStorage.setItem("sakila-ui", JSON.stringify(state)); } catch (e) {} };

/* ------------------------------------------------------------------ tooltip */
const tip = $("#tip");
document.addEventListener("mousemove", e => {
  const t = e.target.closest && e.target.closest("[data-tip]");
  if (!t) { tip.hidden = true; return; }
  tip.innerHTML = t.getAttribute("data-tip"); tip.hidden = false;
  const w = tip.offsetWidth, h = tip.offsetHeight;
  let x = e.clientX + 14, y = e.clientY + 14;
  if (x + w > innerWidth - 8) x = e.clientX - w - 14;
  if (y + h > innerHeight - 8) y = e.clientY - h - 14;
  tip.style.left = x + "px"; tip.style.top = y + "px";
});
document.addEventListener("scroll", () => { tip.hidden = true; }, true);

/* ------------------------------------------------------------------ SVG chart kit */
const W = el => Math.max(300, Math.floor(el.clientWidth || el.parentElement.clientWidth || 600));
const svg = (w, h, body) => `<svg viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" role="img">${body}</svg>`;
const txt = (x, y, s, o = {}) => `<text x="${x}" y="${y}" style="fill:${o.fill || "var(--ink-3)"};font:${o.weight || 400} ${o.size || 11.5}px var(--body)" text-anchor="${o.anchor || "start"}" ${o.baseline ? `dominant-baseline="${o.baseline}"` : ""}>${esc(s)}</text>`;
function niceMax(v) { const p = Math.pow(10, Math.floor(Math.log10(v || 1))); const m = v / p; return ([1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10].find(x => m <= x + 1e-9)) * p; }
function ticks(max, n = 4) { const s = niceMax(max / n); const out = []; for (let v = 0; v <= max + 1e-9; v += s) out.push(v); return out; }

function barV(el, labels, values, o = {}) {
  const w = W(el), h = o.h || 280, L = o.left || 44, R = 10, T = 22, B = 34;
  const max = niceMax(Math.max(...values) * 1.12), ih = h - T - B, iw = w - L - R, bw = iw / labels.length;
  let s = ticks(max).map(v => { const y = T + ih - v / max * ih; return `<line x1="${L}" x2="${w - R}" y1="${y}" y2="${y}" style="stroke:var(--rule)"/>` + txt(L - 6, y, (o.tick || fmt)(v), { anchor: "end", baseline: "middle" }); }).join("");
  labels.forEach((lb, i) => {
    const v = values[i], bh = v / max * ih, x = L + i * bw + bw * .18, y = T + ih - bh, bwid = bw * .64;
    const col = (o.colors && o.colors[i]) || "var(--s1)";
    s += `<path d="M${x},${T + ih} V${y + 4} q0,-4 4,-4 h${bwid - 8} q4,0 4,4 V${T + ih} Z" style="fill:${col}" data-tip="${esc(o.tip ? o.tip(i) : `${lb}<br><b>${(o.val || fmt)(v)}</b>`)}"/>`;
    if (o.labels !== false) s += txt(x + bwid / 2, y - 6, (o.val || fmt)(v), { anchor: "middle", fill: "var(--ink-2)", weight: 600 });
    if (!o.every || i % o.every === 0) s += txt(x + bwid / 2, T + ih + 18, lb, { anchor: "middle" });
  });
  el.innerHTML = svg(w, h, s);
}

function barH(el, labels, values, o = {}) {
  const w = W(el), rowH = o.rowH || 24, L = o.left || 120, R = o.right || 54, T = 6, B = 26;
  const h = T + B + labels.length * rowH, max = o.max || niceMax(Math.max(...values) * 1.05), iw = w - L - R;
  let s = ticks(max, 4).map(v => { const x = L + v / max * iw; return `<line x1="${x}" x2="${x}" y1="${T}" y2="${h - B}" style="stroke:var(--rule)"/>` + txt(x, h - 8, (o.tick || fmt)(v), { anchor: "middle" }); }).join("");
  labels.forEach((lb, i) => {
    const v = values[i], bwid = Math.max(1, v / max * iw), y = T + i * rowH + rowH * .18, bh = rowH * .64;
    const col = (o.colors && o.colors[i]) || "var(--s1)";
    s += txt(L - 8, y + bh / 2, lb, { anchor: "end", baseline: "middle", fill: "var(--ink-2)" });
    s += `<path d="M${L},${y} h${bwid - 4} q4,0 4,4 v${bh - 8} q0,4 -4,4 h${-(bwid - 4)} Z" style="fill:${col}" data-tip="${esc(o.tip ? o.tip(i) : `${lb}<br><b>${(o.val || fmt)(v)}</b>`)}"/>`;
    if (o.labels !== false) s += txt(L + bwid + 6, y + bh / 2, (o.val || fmt)(v), { baseline: "middle", fill: "var(--ink-2)" });
  });
  if (o.ref != null) { const x = L + o.ref / max * iw; s += `<line x1="${x}" x2="${x}" y1="${T - 2}" y2="${h - B}" style="stroke:var(--ink-3);stroke-dasharray:4 4"/>` + txt(x + 4, T + 8, o.refLabel || "", { size: 11 }); }
  el.innerHTML = svg(w, h, s);
}

function stackH(el, labels, series, o = {}) {
  const w = W(el), rowH = 28, L = o.left || 110, R = 16, T = 6, B = 26, h = T + B + labels.length * rowH;
  const tot = labels.map((_, i) => series.reduce((a, s) => a + s.values[i], 0));
  const max = niceMax(Math.max(...tot) * 1.05), iw = w - L - R;
  let s = ticks(max, 4).map(v => { const x = L + v / max * iw; return `<line x1="${x}" x2="${x}" y1="${T}" y2="${h - B}" style="stroke:var(--rule)"/>` + txt(x, h - 8, v.toFixed(3), { anchor: "middle" }); }).join("");
  labels.forEach((lb, i) => {
    let x = L; const y = T + i * rowH + rowH * .18, bh = rowH * .64;
    s += txt(L - 8, y + bh / 2, lb, { anchor: "end", baseline: "middle", fill: "var(--ink-2)", weight: i === 0 ? 700 : 400 });
    series.forEach((se, k) => {
      const bw = se.values[i] / max * iw;
      s += `<rect x="${x}" y="${y}" width="${Math.max(0, bw - (k < series.length - 1 ? 2 : 0))}" height="${bh}" rx="${k === series.length - 1 ? 4 : 0}" style="fill:${se.color}" data-tip="${esc(se.tip(i))}"/>`;
      x += bw;
    });
  });
  el.innerHTML = svg(w, h, s);
}

function lines(el, xs, series, o = {}) {
  const w = W(el), h = o.h || 280, L = 40, R = 14, T = 12, B = 34, iw = w - L - R, ih = h - T - B;
  const max = o.max || niceMax(Math.max(...series.flatMap(s => s.values))), xmin = xs[0], xmax = xs[xs.length - 1];
  const X = v => L + (v - xmin) / (xmax - xmin) * iw, Y = v => T + ih - v / max * ih;
  let s = ticks(max).map(v => `<line x1="${L}" x2="${w - R}" y1="${Y(v)}" y2="${Y(v)}" style="stroke:var(--rule)"/>` + txt(L - 6, Y(v), (o.tick || fmt)(v), { anchor: "end", baseline: "middle" })).join("");
  xs.forEach((x, i) => { if (i % (o.every || 5) === 0 || i === xs.length - 1) s += txt(X(x), h - 12, x, { anchor: "middle" }); });
  if (o.xlabel) s += txt(L + iw / 2, h, o.xlabel, { anchor: "middle", size: 11 });
  series.forEach(se => {
    s += `<path d="${se.values.map((v, i) => `${i ? "L" : "M"}${X(xs[i])},${Y(v)}`).join("")}" style="fill:none;stroke:${se.color};stroke-width:2;${se.dash ? "stroke-dasharray:5 4" : ""}"/>`;
    if (se.dots) se.values.forEach((v, i) => { s += `<circle cx="${X(xs[i])}" cy="${Y(v)}" r="3.5" style="fill:${se.color};stroke:var(--surface);stroke-width:1.5"/>`; });
  });
  const colw = iw / (xs.length - 1);
  xs.forEach((x, i) => { s += `<rect x="${X(x) - colw / 2}" y="${T}" width="${colw}" height="${ih}" style="fill:transparent" data-tip="${esc(o.tip(i))}"/>`; });
  el.innerHTML = svg(w, h, s);
}

function mixHex(a, b, t) {
  const p = h => { h = h.replace("#", ""); return [0, 2, 4].map(i => parseInt(h.slice(i, i + 2), 16)); };
  const A = p(a), B2 = p(b); return "rgb(" + A.map((v, i) => Math.round(v + (B2[i] - v) * t)).join(",") + ")";
}
function ramp(stops, t) { t = Math.max(0, Math.min(1, t)); const n = stops.length - 1, i = Math.min(n - 1, Math.floor(t * n)); return mixHex(stops[i], stops[i + 1], t * n - i); }

function heatmap(el, rows, cols, M, o) {
  const w = W(el), L = 92, T = 8, B = 86, R = 8, cw = (w - L - R) / cols.length, ch = Math.min(28, Math.max(20, cw * .8)), h = T + B + rows.length * ch;
  const seq = ["--heat-0", "--heat-1", "--heat-2", "--heat-3", "--heat-4"].map(cssv);
  const div = [cssv("--div-lo"), cssv("--div-mid"), cssv("--div-hi")];
  let s = "";
  rows.forEach((r, i) => {
    s += txt(L - 6, T + i * ch + ch / 2, r, { anchor: "end", baseline: "middle", fill: "var(--ink-2)" });
    cols.forEach((c, j) => {
      const v = M[i][j], col = o.diverging ? ramp(div, (v - o.min) / (o.max - o.min)) : ramp(seq, (v - o.min) / (o.max - o.min));
      s += `<rect x="${L + j * cw + 1}" y="${T + i * ch + 1}" width="${cw - 2}" height="${ch - 2}" rx="2" style="fill:${col}" data-tip="${esc(o.tip(i, j))}"/>`;
    });
  });
  cols.forEach((c, j) => { const x = L + j * cw + cw / 2, y = T + rows.length * ch + 8; s += `<text transform="translate(${x},${y}) rotate(-45)" text-anchor="end" style="fill:var(--ink-2);font:400 11.5px var(--body)">${esc(c)}</text>`; });
  s += txt(L + (w - L - R) / 2, h - 4, "next category (B) →", { anchor: "middle", size: 11 });
  el.innerHTML = svg(w, h, s);
}

function scatter(el, pts, o) {
  const w = W(el), h = 300, L = 54, R = 16, T = 12, B = 38, iw = w - L - R, ih = h - T - B;
  const X = v => L + (v - o.xmin) / (o.xmax - o.xmin) * iw, Y = v => T + ih - (v - o.ymin) / (o.ymax - o.ymin) * ih;
  let s = "";
  for (let v = o.ymin; v <= o.ymax + 1e-9; v += o.ystep) s += `<line x1="${L}" x2="${w - R}" y1="${Y(v)}" y2="${Y(v)}" style="stroke:var(--rule)"/>` + txt(L - 6, Y(v), v.toFixed(2), { anchor: "end", baseline: "middle" });
  for (let v = o.xmin; v <= o.xmax + 1e-9; v += o.xstep) s += txt(X(v), h - 18, fmt(v), { anchor: "middle" });
  s += txt(L + iw / 2, h - 2, o.xlabel, { anchor: "middle", size: 11 });
  pts.forEach(p => { s += `<circle cx="${X(p.x)}" cy="${Y(p.y)}" r="6" style="fill:var(--s1);stroke:var(--surface);stroke-width:2" data-tip="${esc(p.tip)}"/>`; });
  el.innerHTML = svg(w, h, s);
}

function journeyPlot(el, j) {
  const cats = [...new Set(j.map(x => x.category))].sort();
  const w = W(el), L = 96, R = 12, T = 10, rowH = 20, B = 34, h = T + B + cats.length * rowH, iw = w - L - R;
  const X = k => L + (k - 1) / Math.max(1, j.length - 1) * iw, Y = c => T + cats.indexOf(c) * rowH + rowH / 2;
  let s = cats.map(c => `<line x1="${L}" x2="${w - R}" y1="${Y(c)}" y2="${Y(c)}" style="stroke:var(--rule)"/>` + txt(L - 8, Y(c), c, { anchor: "end", baseline: "middle", fill: "var(--ink-2)" })).join("");
  s += `<path d="${j.map((x, i) => `${i ? "L" : "M"}${X(x.rental_number)},${Y(x.category)}`).join("")}" style="fill:none;stroke:var(--rule-strong);stroke-width:1.5"/>`;
  const col = { switch: "var(--s1)", repeat: "var(--s2)", "first rental": "var(--s-gray)" };
  j.forEach(x => { s += `<circle cx="${X(x.rental_number)}" cy="${Y(x.category)}" r="5.5" style="fill:${col[x.transition]};stroke:var(--surface);stroke-width:2" data-tip="${esc(`#${x.rental_number} · <b>${x.category}</b> (${x.transition})<br>${title(x.title)}<br>${x.rental_date}`)}"/>`; });
  for (let k = 1; k <= j.length; k += (j.length > 30 ? 5 : 4)) s += txt(X(k), h - 14, k, { anchor: "middle" });
  s += txt(L + iw / 2, h, "rental number", { anchor: "middle", size: 11 });
  el.innerHTML = svg(w, h, s);
}

/* ------------------------------------------------------------------ helpers */
const note = (html, kind = "") => `<div class="note ${kind}">${kind === "caution" ? '<b class="tag">Caution</b>' : kind === "" ? '<b class="tag">Finding</b>' : ""}${html}</div>`;
const kpi = (l, v, s = "") => `<div class="kpi"><div class="l">${l}</div><div class="v">${v}</div><div class="s">${s}</div></div>`;
const chipsHTML = (cs, max = 10) => { const it = cs.slice(-max); return `<div class="chips">${cs.length > max ? '<span class="chip">…</span><span class="arr">→</span>' : ""}${it.map((c, i) => `<span class="chip ${i === it.length - 1 ? "last" : ""}">${esc(c)}</span>`).join('<span class="arr">→</span>')}</div>`; };
const table = (cols, rows) => `<div class="tablewrap"><table><thead><tr>${cols.map(c => `<th class="${c.num ? "num" : ""}">${c.h}</th>`).join("")}</tr></thead><tbody>${rows.map(r => `<tr>${cols.map(c => `<td class="${c.num ? "num" : ""}">${c.f ? c.f(r) : esc(r[c.k])}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
const seg = (id, opts, cur) => `<div class="seg" id="${id}">${opts.map(([v, l]) => `<button type="button" data-v="${v}" aria-pressed="${v === cur}">${l}</button>`).join("")}</div>`;
const customerOptions = sel => Object.keys(D.customers).map(id => `<option value="${id}" ${+id === +sel ? "selected" : ""}>${id} · ${esc(D.customers[id].n)}</option>`).join("");
const H = D.headline, IT = D.independence, RP = D.repetition, DV = D.diversity, RS = D.return;
const draws = []; // re-render hooks for resize / theme

/* ------------------------------------------------------------------ pages */
const PAGES = {};

PAGES.overview = () => {
  const cp = [...D.category_perf].sort((a, b) => b.rentals - a.rentals);
  const lo = cp[cp.length - 1], hi = cp[0];
  const peak = D.monthly.reduce((a, b) => b.rentals > a.rentals ? b : a);
  return `
  <div><div class="kicker">Sakila DVD rental · ${H.first_rental.slice(0, 10)} → ${H.last_rental.slice(0, 10)}</div>
  <h1>Customers return. Do they stay in one category?</h1>
  <p class="lede">A business-intelligence study of Sakila's 599 customers. Every figure on these pages comes from SQL and Python run on the official Sakila data.</p></div>
  <div class="kpis">
    ${kpi("Total customers", fmt(H.total_customers), `${fmt(H.renting_customers)} rented in window`)}
    ${kpi("Total rentals", fmt(H.total_rentals), "consecutive pairs analysed: " + fmt(RP.transitions))}
    ${kpi("Total revenue", money(H.total_revenue), "sum of payments in window")}
    ${kpi("Avg rental rate", money(H.avg_catalog_rental_rate), `catalogue avg · ${money(H.avg_payment_per_rental)} paid per rental`)}
    ${kpi("Most rented category", H.most_rented_category, `${fmt(H.most_rented_category_rentals)} rentals`)}
  </div>
  <div class="story">
    <a href="#exploration"><span class="n">Step 1</span><span class="q">Do customers return?</span><span class="a">Yes: ${RS.pct_customers_returning}% rent more than once.</span></a>
    <a href="#exploration"><span class="n">Step 2</span><span class="q">Do they repeat a category?</span><span class="a">Rarely: ${RP.switch_pct}% of next rentals switch.</span></a>
    <a href="#transitions"><span class="n">Step 3</span><span class="q">Where do they go next?</span><span class="a">Almost anywhere: χ² p = ${IT.p_value.toFixed(2)}.</span></a>
    <a href="#recommend"><span class="n">Step 4</span><span class="q">What should we recommend?</span><span class="a">A transparent, data-based suggestion.</span></a>
    <a href="#agent"><span class="n">Step 5</span><span class="q">Explain it</span><span class="a">An AI agent that answers from the data.</span></a>
  </div>
  <div class="grid2">
    <div class="panel"><h3>Rentals per month</h3><div class="chart" id="c-mr"></div></div>
    <div class="panel"><h3>Revenue per month</h3><div class="sub">Payments dated inside the analysis window</div><div class="chart" id="c-mv"></div></div>
  </div>
  ${note(`Activity peaks in <b>${peak.month}</b> (${fmt(peak.rentals)} rentals). Rentals fall on only <b>${RS.distinct_rental_dates_in_window} distinct dates</b>, so Sakila records rentals in bursts rather than as a continuous daily stream. Read month-to-month trends with that in mind.`, "neutral")}
  <div class="panel"><h3>Daily rentals</h3><div class="sub">Only dates with recorded rentals appear</div><div class="chart" id="c-daily"></div></div>
  <div class="grid2">
    <div class="panel"><h3>Rentals by category</h3><div class="sub">Dashed line = a perfectly equal split</div><div class="chart" id="c-cat"></div></div>
    <div style="display:flex;flex-direction:column;gap:14px">
      ${note(`Demand is spread <b>almost evenly</b> across the ${cp.length} categories. Shares run from ${lo.rental_share_pct.toFixed(2)}% (${lo.category}) to ${hi.rental_share_pct.toFixed(2)}% (${hi.category}); a perfectly equal split would be 6.25%. No single genre dominates.`)}
      ${table([{ h: "Category", k: "category" }, { h: "Rentals", num: 1, f: r => fmt(r.rentals) }, { h: "Share", num: 1, f: r => r.rental_share_pct.toFixed(2) + "%" }, { h: "Revenue", num: 1, f: r => money(r.revenue) }], cp)}
    </div>
  </div>`;
};
draws.push(["overview", () => {
  const m = D.monthly, labels = m.map(r => new Date(r.month + "-01T00:00").toLocaleString("en-US", { month: "short", year: "numeric" }));
  barV($("#c-mr"), labels, m.map(r => r.rentals));
  barV($("#c-mv"), labels, m.map(r => r.revenue), { val: v => "$" + fmt(v), tick: v => "$" + fmt(v / 1000) + "k", left: 48 });
  const d = D.daily;
  barV($("#c-daily"), d.map(r => r.date.slice(5)), d.map(r => r.rentals), { labels: false, h: 220, every: W($("#c-daily")) < 700 ? 8 : 4, tip: i => `${d[i].date}<br><b>${fmt(d[i].rentals)}</b> rentals · ${money(d[i].revenue)}` });
  const cp = [...D.category_perf].sort((a, b) => b.rentals - a.rentals);
  barH($("#c-cat"), cp.map(r => r.category), cp.map(r => r.rentals), { left: 96, ref: H.total_rentals / cp.length, refLabel: "equal share",
    tip: i => `${cp[i].category}<br><b>${fmt(cp[i].rentals)}</b> rentals (${cp[i].rental_share_pct.toFixed(2)}%)<br>${money(cp[i].revenue)} revenue` });
}]);

PAGES.exploration = () => `
  <div><div class="kicker">Steps 1–2</div><h1>They come back, and they move around</h1>
  <p class="lede">First we check whether customers return. Then we check what they pick when they do.</p></div>
  <h2>Step 1 · Do customers return?</h2>
  <div class="kpis">
    ${kpi("Customers who rent again", RS.pct_customers_returning.toFixed(0) + "%", `${RS.customers_with_2plus_rentals} of ${RS.customers_with_rentals}`)}
    ${kpi("Rentals per customer", fmt(RS.rentals_per_customer_median), `median · range ${RS.rentals_per_customer_min}–${RS.rentals_per_customer_max}`)}
    ${kpi("Visit days per customer", fmt(RS.visit_days_per_customer_median), "median distinct rental dates")}
    ${kpi("Active in every month", RS.pct_active_in_all_months.toFixed(1) + "%", `of customers · ${RS.months_in_window} months in window`)}
  </div>
  ${note(`All ${RS.customers_with_rentals} customers return, and even the lightest customer has ${RS.rentals_per_customer_min} rentals. Retention is not the issue for Sakila. The real question is <b>what customers choose when they come back</b>.`)}
  <h2>Step 2 · Category loyalty vs category exploration</h2>
  <div class="kpis">
    ${kpi("Next rental switches category", RP.switch_pct.toFixed(2) + "%", `${fmt(RP.switched_category)} of ${fmt(RP.transitions)} transitions`)}
    ${kpi("Next rental repeats category", RP.repeat_pct.toFixed(2) + "%", `${fmt(RP.same_category)} transitions`)}
    ${kpi("Categories explored", `${DV.median_distinct_categories} / ${DV.total_categories}`, "median per customer")}
    ${kpi("Favourite category share", DV.median_top_category_share_pct.toFixed(0) + "%", "median share of a customer's top category")}
  </div>
  <div class="grid2">
    <div class="panel"><h3>Same-category repeat rate vs chance</h3><div class="sub">% of consecutive rentals that stay in the same category</div><div class="chart" id="c-rep"></div></div>
    <div class="panel"><h3>Customers by number of categories rented</h3><div class="sub">out of 16 categories</div><div class="chart" id="c-div"></div></div>
  </div>
  ${note(`<b>${RP.switch_pct.toFixed(1)}%</b> of consecutive rentals move to a different category, and ${DV.pct_customers_10plus_categories.toFixed(0)}% of customers have rented 10 or more of the 16 categories. Customers clearly <b>return and explore</b>.`)}
  ${note(`But the repeat rate (${RP.repeat_pct}%) is close to what pure chance would produce. Picking categories at random gives ${RP.random_choice_repeat_pct}%, and shuffling each customer's own history gives ${RP.shuffled_sequence_repeat_pct}% (p = ${RP.shuffled_repeat_p_value}, ${RP.n_permutations} shuffles). So switching is simply what happens when customers choose among 16 categories with similar demand. It is not evidence of a special appetite for novelty. The result holds when only rentals on different days are counted (${RP.different_day_repeat_pct}% repeats).`, "caution")}
  <details><summary>SQL used: repeat vs switch</summary><pre class="sql">${esc(SQL.repeat_vs_switch || "")}</pre></details>
  <div class="panel"><h3>How fast do customers discover new categories?</h3><div class="sub">Share of rentals in a category the customer had never rented before</div>
    <div class="legend"><span><i style="background:var(--s1)"></i>Observed</span><span><i class="dash"></i>Shuffled baseline</span></div><div class="chart" id="c-disc"></div></div>
  ${(() => { const d = D.discovery; const a = d.find(r => r.rental_number === 2), b = d.find(r => r.rental_number === 10);
    return note(`At rental #2, ${a.observed_new_category_pct.toFixed(1)}% of customers choose a category they haven't tried before. By rental #10 the figure is still ${b.observed_new_category_pct.toFixed(1)}%. It falls only because customers run out of untried categories: the observed curve closely follows the shuffled baseline.`, "neutral"); })()}
  <h2>Customer journey examples</h2>
  <div class="controls"><label class="field" for="jc">Customer<select id="jc">${customerOptions(state.journeyCustomer)}</select></label></div>
  <div id="jview"></div>`;
draws.push(["exploration", () => {
  barV($("#c-rep"), ["Observed in Sakila", "Shuffled own history", "Random choice (Σp²)"], [RP.repeat_pct, RP.shuffled_sequence_repeat_pct, RP.random_choice_repeat_pct],
    { colors: ["var(--s1)", "var(--s-gray)", "var(--s-gray)"], val: v => v.toFixed(2) + "%", tick: v => v + "%" });
  const dist = Object.entries(DV.distribution).map(([k, v]) => [k, v]);
  barV($("#c-div"), dist.map(x => x[0]), dist.map(x => x[1]), { tip: i => `${dist[i][0]} categories<br><b>${dist[i][1]}</b> customers` });
  const d = D.discovery;
  lines($("#c-disc"), d.map(r => r.rental_number), [
    { values: d.map(r => r.observed_new_category_pct), color: "var(--s1)", dots: true },
    { values: d.map(r => r.shuffled_baseline_pct), color: "var(--s-gray)", dash: true }],
    { max: 100, tick: v => v + "%", xlabel: "rental number in the customer's history", tip: i => `Rental #${d[i].rental_number}<br>Observed <b>${d[i].observed_new_category_pct.toFixed(1)}%</b><br>Shuffled ${d[i].shuffled_baseline_pct.toFixed(1)}%<br>${d[i].customers} customers` });
  renderJourney();
}]);
function renderJourney() {
  const cid = state.journeyCustomer, j = E.journey(cid), s = D.summary[cid];
  $("#jview").innerHTML = `${chipsHTML(j.map(x => x.category), 12)}
    <p class="lede" style="margin-top:8px;font-size:13.5px">${esc(D.customers[cid].n)} · ${esc(D.customers[cid].loc)} · ${j.length} rentals · ${s[0]} categories · repeat rate ${(100 * s[1]).toFixed(1)}% · favourite: ${s[2]} (${(100 * s[3]).toFixed(0)}%)</p>
    <div class="panel"><div class="legend"><span><i style="background:var(--s1)"></i>switch</span><span><i style="background:var(--s2)"></i>repeat</span><span><i style="background:var(--s-gray)"></i>first rental</span></div><div class="chart" id="c-journey"></div>
    <div class="sub">Rentals with the same timestamp are ordered by rental_id (a fixed tie-breaker).</div></div>`;
  journeyPlot($("#c-journey"), j);
}

PAGES.transitions = () => `
  <div><div class="kicker">Step 3 · the core analysis</div><h1>After category A, where do customers go?</h1>
  <p class="lede">We sort each customer's rentals by time (rental_date, with rental_id breaking ties) and pair each rental with the next one. That gives ${fmt(IT.n_transitions)} observed moves from category A to category B.</p></div>
  <div class="kpis">
    ${kpi("Transitions analysed", fmt(IT.n_transitions), "consecutive rental pairs")}
    ${kpi("Highest P(B | A)", pct(IT.max_probability), "chance level = 6.25%")}
    ${kpi("Independence test", "p = " + IT.p_value.toFixed(2), `χ² = ${fmt(IT.chi2)}, dof ${IT.dof}`)}
    ${kpi("Association strength", "V = " + IT.cramers_v.toFixed(3), "Cramér's V (below 0.1 = negligible)")}
  </div>
  ${note(`<b>Key result:</b> the previous category tells us very little about the next one. There is no evidence that the previous category changes which category comes next (χ² p = ${IT.p_value}, Cramér's V = ${IT.cramers_v}). Only ${IT.cells_abs_z_gt_1_96} of ${IT.cells} cells deviate at |z| > 1.96, about the ${Math.round(IT.cells_expected_by_chance_at_5pct)} you'd expect by chance. <b>${IT.cells_significant_after_bonferroni}</b> survive a Bonferroni correction (|z| > ${IT.bonferroni_z_threshold}).`, "caution")}
  <div class="panel">
    <div style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;align-items:center"><h3 style="margin:0">Transition heatmap · rows = previous category (A)</h3>
    ${seg("heatmode", [["prob", "P(B | A)"], ["lift", "Lift vs baseline"], ["count", "Counts"]], state.heat)}</div>
    <div class="sub" id="heatsub"></div><div class="chart" id="c-heat"></div><div class="scale" id="heatscale"></div>
  </div>
  ${(() => { const P = E.P.flat(); return note(`Across every row, the cells run from <b>${pct(Math.min(...P))}</b> to <b>${pct(Math.max(...P))}</b>. That's a narrow band around the 6.25% you'd get by picking one of 16 categories at random. The heatmap looks flat, and that flatness is the finding.`, "neutral"); })()}
  <details><summary>SQL used: transition counts</summary><pre class="sql">${esc(SQL.transition_counts || "")}</pre></details>
  <h2>Most frequent category switches (A ≠ B)</h2>
  <div class="grid2">
    <div class="panel"><div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;align-items:center"><h3 style="margin:0">Top 15</h3>${seg("rankby", [["transitions", "Count"], ["probability", "Probability"], ["lift", "Lift"]], state.rankBy)}</div><div class="chart" id="c-top" style="margin-top:8px"></div></div>
    <div style="display:flex;flex-direction:column;gap:14px">${(() => { const a = E.topTransitions(1)[0], b = E.topTransitions(1, "probability")[0];
      return note(`The most frequent switch is <b>${a.from_category} → ${a.to_category}</b> (${a.transitions} times, P = ${pct(a.probability)}). The highest conditional probability is <b>${b.from_category} → ${b.to_category}</b> (${pct(b.probability)}, lift ${b.lift.toFixed(2)}, z = ${b.z_residual.toFixed(2)}).`) +
      note("The frequency ranking mostly reflects category size: Sports and Animation are the biggest categories, so they appear in the most pairs. None of these pairs can be distinguished from chance once you correct for 256 comparisons. Describe them as <i>historically observed</i>, not as reliable routes.", "caution"); })()}</div>
  </div>
  <h2>Where do customers go after…</h2>
  <div class="controls"><label class="field" for="fromcat">Category A<select id="fromcat">${D.categories.map(c => `<option ${c === state.fromCat ? "selected" : ""}>${c}</option>`).join("")}</select></label></div>
  <div class="panel"><h3 id="fromtitle"></h3><div class="sub">Dashed line = 6.25% chance level</div><div class="chart" id="c-from"></div><div class="sub" id="fromnote"></div></div>
  <h2>Is there a gateway category?</h2>
  <p class="lede"><b>Definition used.</b> A gateway category would have to send customers to many destinations in a way that stands out from other categories. That means unusually strong routes (significant cells) or an unusually broad spread (outgoing entropy). High rental volume on its own doesn't count.</p>
  <div class="grid2">
    <div class="panel"><h3>Outgoing volume vs spread of destinations</h3><div class="sub">normalized entropy: 1 = perfectly even spread</div><div class="chart" id="c-ent"></div></div>
    ${table([{ h: "Category", k: "category" }, { h: "Out", num: 1, k: "outgoing_transitions" }, { h: "In", num: 1, k: "incoming_transitions" }, { h: "Dest.", num: 1, k: "unique_destinations" }, { h: "Entropy", num: 1, f: r => r.outgoing_entropy.toFixed(4) }, { h: "Strongest →", k: "strongest_destination" }, { h: "P", num: 1, f: r => pct(r.strongest_probability) }, { h: "z", num: 1, f: r => r.strongest_z.toFixed(2) }], D.high_transition)}
  </div>
  ${note(`<b>Verdict: the data does not support a gateway category.</b> ${esc(D.gateway.explanation)}`, D.gateway.gateway_supported ? "" : "caution")}`;
draws.push(["transitions", () => { drawHeat(); drawTop(); drawFrom();
  const ht = D.high_transition, xs = ht.map(r => r.outgoing_transitions);
  scatter($("#c-ent"), ht.map(r => ({ x: r.outgoing_transitions, y: r.outgoing_entropy, tip: `<b>${r.category}</b><br>${r.outgoing_transitions} outgoing<br>entropy ${r.outgoing_entropy.toFixed(4)}` })),
    { xmin: Math.floor(Math.min(...xs) / 100) * 100, xmax: Math.ceil(Math.max(...xs) / 100) * 100, xstep: 100, ymin: 0.9, ymax: 1.0, ystep: 0.02, xlabel: "outgoing transitions" });
}]);
function drawHeat() {
  const cats = D.categories, m = state.heat;
  let M, o;
  if (m === "prob") { M = E.P.map(r => r.map(v => 100 * v)); o = { min: 0, max: 15, tip: (i, j) => `${cats[i]} → <b>${cats[j]}</b><br>P = ${M[i][j].toFixed(2)}%<br>${E.C[i][j]} transitions` };
    $("#heatsub").textContent = "Colour scale anchored at 0–15%, so small differences aren't visually exaggerated. Hover a cell for exact values."; }
  else if (m === "lift") { M = E.lift; const dev = Math.max(...M.flat().map(v => Math.abs(v - 1))); o = { diverging: true, min: 1 - dev, max: 1 + dev, tip: (i, j) => `${cats[i]} → <b>${cats[j]}</b><br>lift ${M[i][j].toFixed(2)} · z ${E.Z[i][j].toFixed(2)}<br>${E.C[i][j]} transitions` };
    $("#heatsub").textContent = "Lift = P(B|A) ÷ B's overall share. Blue = below 1, red = above 1, grey = exactly as expected."; }
  else { M = E.C; o = { min: 0, max: Math.max(...M.flat()), tip: (i, j) => `${cats[i]} → <b>${cats[j]}</b><br>${M[i][j]} transitions` };
    $("#heatsub").textContent = "Raw counts of consecutive-rental pairs."; }
  heatmap($("#c-heat"), cats, cats, M, o);
  const stops = o.diverging ? ["--div-lo", "--div-mid", "--div-hi"] : ["--heat-0", "--heat-1", "--heat-2", "--heat-3", "--heat-4"];
  const lab = m === "prob" ? ["0%", "7.5%", "15%"] : m === "lift" ? [o.min.toFixed(2), "1.00", o.max.toFixed(2)] : ["0", fmt(o.max / 2), fmt(o.max)];
  $("#heatscale").innerHTML = `<span>${lab[0]}</span><span class="bar" style="background:linear-gradient(90deg,${stops.map(v => cssv(v)).join(",")})"></span><span>${lab[2]}</span><span style="margin-left:6px">(midpoint ${lab[1]})</span>`;
}
function drawTop() {
  const k = state.rankBy, t = E.topTransitions(15, k);
  barH($("#c-top"), t.map(r => `${r.from_category} → ${r.to_category}`), t.map(r => r[k]), { left: 168, rowH: 22,
    val: k === "probability" ? v => pct(v) : k === "lift" ? v => v.toFixed(2) : fmt, tick: k === "probability" ? v => pct(v, 0) : k === "lift" ? v => v.toFixed(1) : fmt,
    tip: i => `${t[i].from_category} → <b>${t[i].to_category}</b><br>${t[i].transitions} transitions · P = ${pct(t[i].probability)}<br>lift ${t[i].lift.toFixed(2)} · z ${t[i].z_residual.toFixed(2)}` });
}
function drawFrom() {
  const p = E.categoryProfile(state.fromCat, "outgoing", 15), d = p.top_destinations;
  $("#fromtitle").textContent = `P(next = B | previous = ${p.category}) · ${fmt(p.outgoing_transitions)} transitions`;
  barH($("#c-from"), d.map(r => r.to_category), d.map(r => r.probability), { left: 96, max: 0.1, ref: 1 / 16, refLabel: "chance", val: v => pct(v), tick: v => pct(v, 0),
    tip: i => `<b>${d[i].to_category}</b><br>P = ${pct(d[i].probability)} (${d[i].transitions} transitions)<br>lift ${d[i].lift} · z ${d[i].z_residual}` });
  $("#fromnote").textContent = `${p.category} is followed by ${p.category} again ${pct(p.self_transition_probability)} of the time, and it reaches all ${p.unique_destination_categories} other categories.`;
}

PAGES.recommend = () => `
  <div><div class="kicker">Step 4</div><h1>Next-category recommendation</h1>
  <p class="lede">A transparent score that combines historical Sakila transitions with the customer's own history. It picks a category first, then movies from that category.</p></div>
  <div class="controls">
    <label class="field" for="rc">Customer<select id="rc">${customerOptions(state.customer)}</select></label>
    <label class="toggle" for="rx"><input type="checkbox" id="rx" ${state.exploration ? "checked" : ""}> Exploration mode (exclude the current category)</label>
    <label class="toggle" for="rs"><input type="checkbox" id="rs" ${state.inStock ? "checked" : ""}> Only in-stock movies</label>
  </div>
  <div id="rview"></div>`;
draws.push(["recommend", renderReco]);
function renderReco() {
  const r = E.recommend(state.customer, { exploration: state.exploration, availableOnly: state.inStock, nMovies: 6, nCategories: 4 });
  const j = E.journey(state.customer), s = D.settings;
  lastReco = { customer_id: r.customer_id, category: r.recommended_category };
  const bt = D.backtest;
  $("#rview").innerHTML = `
    <h2 style="margin-top:0">Customer journey <span style="font-weight:500;color:var(--ink-3);font-size:14px">(most recent on the right)</span></h2>
    ${chipsHTML(j.map(x => x.category), 10)}
    <div class="kpis">
      ${kpi("Current category", r.current_category, "last rental " + r.last_rental_date.slice(0, 10))}
      ${kpi("Recommended next category", r.recommended_category, r.mode)}
      ${kpi("Transition probability", pct(r.transition_probability), `${r.transitions_observed} of ${fmt(r.outgoing_transitions_from_current)} · lift ${r.lift_vs_baseline.toFixed(2)}`)}
      ${kpi("Signal strength", r.signal_strength === "weak" ? "Weak" : "Moderate", `z = ${r.z_residual.toFixed(2)} · matrix p = ${r.global_signal.chi2_p_value.toFixed(2)}`)}
    </div>
    <h2>Why this category?</h2>
    ${note(`The customer's most recent rental was <b>${r.current_category}</b>. Across all Sakila rental sequences, <b>${r.transitions_observed}</b> of the ${fmt(r.outgoing_transitions_from_current)} rentals that followed a ${r.current_category} rental were <b>${r.recommended_category}</b> (P = ${pct(r.transition_probability)}, lift ${r.lift_vs_baseline.toFixed(2)}). This customer has rented ${r.customer_rentals_in_recommended_category} ${r.recommended_category} film(s) out of ${r.rentals_in_window} (smoothed affinity ${pct(r.customer_affinity, 1)}). Combining the two (score = ${s.w_t} × transition + ${s.w_a} × affinity), <b>${r.recommended_category}</b> ranks first with a score of ${r.score.toFixed(4)}.`)}
    ${note(`The signal is <b>${r.signal_strength}</b>: in Sakila, the move from one category to the next is close to chance (χ² p = ${r.global_signal.chi2_p_value.toFixed(2)}, Cramér's V = ${r.global_signal.cramers_v.toFixed(3)}). Treat the category as a suggestion informed by the data. Most of the practical value comes from the movie ranking: popular films, in stock, that the customer hasn't seen.`, "caution")}
    <div class="panel"><h3>Category score breakdown (top 8)</h3>
      <div class="legend"><span><i style="background:var(--s1)"></i>Transition probability part</span><span><i style="background:var(--s2)"></i>Customer affinity part</span></div>
      <div class="chart" id="c-score"></div></div>
    <h2>Recommended ${esc(r.recommended_category)} movies</h2>
    <p class="lede" style="font-size:13.5px">Rule: films in the recommended category that this customer has never rented${state.inStock ? ", with at least one copy in stock" : ""}. They are ranked by rentals in the analysis window (popularity), then by copies available.</p>
    <div class="movies">${r.recommended_movies.map((m, i) => `<div class="movie"><span class="rank">#${i + 1} · ${esc(m.category)}</span><span class="t">${esc(m.title.toLowerCase())}</span>
      <span class="m"><span class="badge">${m.rating}</span><span>$${m.rental_rate}</span><span>${m.length} min</span></span>
      <span class="m">${m.rentals_in_window} rentals · ${m.available_copies}/${m.copies} copies in stock</span></div>`).join("") || "<p>No eligible movies.</p>"}</div>
    ${Object.keys(r.alternative_category_movies).length ? `<p class="lede" style="font-size:13.5px"><b>Alternatives from the next-ranked categories:</b> ${Object.entries(r.alternative_category_movies).map(([c, t]) => `<i>${c}</i>: ${t.map(title).join(", ")}`).join(" · ")}</p>` : ""}
    <details><summary>Full rental history (${j.length} rentals)</summary><div style="margin-top:10px">${table([{ h: "#", num: 1, k: "rental_number" }, { h: "Date", f: x => x.rental_date.slice(0, 10) }, { h: "Title", f: x => esc(title(x.title)) }, { h: "Category", k: "category" }, { h: "Step", k: "transition" }], j)}</div></details>
    <details><summary>How well does next-category prediction work? (hold-out test)</summary>
      <div class="chart" id="c-bt" style="margin-top:10px"></div>
      <p class="lede" style="font-size:13.5px">Each of the ${bt.customers_tested} customers had their last rental hidden. Transitions and popularity were learned from the remaining rentals, and each method tried to predict the hidden category. With a standard error of about ±${bt["standard_error_hit@3_pp"]} percentage points, every method performs roughly like a random guess. That matches the independence test.</p></details>`;
  const rk = r.ranked_categories.slice(0, 8), tot = s.w_t + s.w_a;
  stackH($("#c-score"), rk.map(x => x.category), [
    { color: "var(--s1)", values: rk.map(x => s.w_t / tot * x.transition_probability), tip: i => `<b>${rk[i].category}</b><br>P = ${pct(rk[i].transition_probability)} (${rk[i].transitions_from_last} transitions)<br>contributes ${(s.w_t / tot * rk[i].transition_probability).toFixed(4)}` },
    { color: "var(--s2)", values: rk.map(x => s.w_a / tot * x.affinity), tip: i => `<b>${rk[i].category}</b><br>affinity ${pct(rk[i].affinity)} (${rk[i].customer_rentals_in_category} rentals)<br>contributes ${(s.w_a / tot * rk[i].affinity).toFixed(4)}` }]);
  barV($("#c-bt"), ["Random guess", "Most popular", "Transition only", "This app (blend)"], [bt["random_hit@3_pct"], bt["popularity_hit@3_pct"], bt["transition_only_hit@3_pct"], bt["app_blend_hit@3_pct"]],
    { colors: ["var(--s-gray)", "var(--s1)", "var(--s1)", "var(--s1)"], val: v => v.toFixed(2) + "%", tick: v => v + "%", h: 240 });
}
let lastReco = null;

/* ------------------------------------------------------------------ AI agent */
const STOPW = new Set("a an the of to in for is are was were be do does did what which who how why can could should would will i me my we our you your it its that this these those and or on at by with from as if than then there their sakila customer customers".split(" "));
const SYN = { bundle: ["combo", "bulk", "price"], combo: ["bulk", "price"], pricing: ["price"], forecast: ["predict", "demand"], older: ["age", "group"], age: ["group"],
  lose: ["lose", "revenue"], lost: ["lose", "revenue"], branches: ["stores"], branch: ["stores"], shops: ["stores"], trend: ["trend", "months"], trends: ["trend", "months"],
  valentine: ["valentine's", "february"], bcg: ["bcg", "matrix"], invest: ["invest", "totally"] };
const toks = t => (String(t).toLowerCase().replace(/-/g, " ").match(/[a-z0-9$.']+/g) || []).filter(w => !STOPW.has(w) && w.length > 1);
function guidanceFor(q, k = 2, min = 0.22) {
  const docs = D.testbank.map(e => new Set(toks(e.q))), df = {};
  docs.forEach(d => d.forEach(w => df[w] = (df[w] || 0) + 1));
  const idf = w => Math.log(1 + docs.length / (df[w] || docs.length));
  const Q = new Set(toks(q)); [...Q].forEach(w => (SYN[w] || []).forEach(x => Q.add(x)));
  if (!Q.size) return [];
  return D.testbank.map((e, i) => { const d = docs[i]; let inter = 0, uni = 0; const u = new Set([...Q, ...d]);
      u.forEach(w => { const v = df[w] ? idf(w) : 1; uni += v; if (Q.has(w) && d.has(w)) inter += v; }); return { e, sc: inter / (uni || 1) }; })
    .sort((x, y) => y.sc - x.sc).slice(0, k).filter(x => x.sc >= min).map(x => x.e);
}
const RULES = (q = "") => {
  const g = guidanceFor(q);
  return `You are the Sakila AI Business Agent, a senior analyst for the Sakila DVD rental chain (2 stores). Audiences: business users (managers, lecturers, analysts) and shoppers ("hi, I want a history DVD"). Use ONLY data from the tools (they query the real Sakila data).

CORE RULES
1. Every number, category, title, store or customer fact MUST come from a tool result in this conversation. Never guess; never infer a fact from the ABSENCE of information; if no tool covers it, say the data does not contain it. If the user says you are wrong, re-check with a tool and admit mistakes. Copy numbers exactly; label any illustrative number "illustrative". State scope (analysis window vs all 16,044 rentals). No HTML tags.
2. THE INSIGHTS: the team report has exactly SIX insights. "How many / what are the insights" -> get_insights() and list all six. Details, metrics, SQL -> get_insights(insight_id). Present verified_findings; mention report_check items when they correct the written report. Do not invent other insights.
3. Before answering about causes/effects, forecasts, profit/cost, motives or satisfaction, demographics or personas, visits/baskets, churn/lifetime value, market share, BCG, pricing changes or "what if" scenarios, call get_data_limitations and structure the answer as (a) what the data shows with numbers, (b) what it cannot show and why, (c) a proxy or test design. Refuse false premises politely.
4. Association is not causation. Counterfactuals cannot be measured. Lucas critique: relationships observed under current policies (fixed prices, no bundles, current due dates) may change once the policy changes, so recommend a controlled pilot/A-B test with KPIs.
5. Time: rentals exist only on 41 dates in five 8-day bursts (May-Aug 2005) plus 2006-02-14, with a 174-day gap; Sep 2005-Jan 2006 are MISSING, not zero. Use get_trends and warn; never state growth rates, seasonality or monthly churn as facts.
6. Never recommend investing everything in one title/category (demand is spread evenly; customers switch category 93% of the time). A real BCG needs market growth and relative market share, which Sakila lacks; only an internal proxy with that warning.
7. Metrics: define exactly as in metrics_to_watch / field_meanings. Lift 1.4 = 1.4x the baseline share, not 140%. The permutation p (repeat vs shuffled) is NOT the chi-square p (transition independence).
8. Charts: this web page shows charts in its dashboard tabs (1-4); point to the relevant tab. SQL requests: give each insight's follow_up_sql in sql code blocks.
9. REPORT / STORY MODE: consulting (MBB) structure, Pyramid Principle, MECE: # action title stating the answer; Executive summary (situation, complication, resolution); Key findings per insight (headline -> evidence -> implication); Recommendations as testable initiatives (owner, KPI, pilot); Risks & data limitations; Next steps (30/60/90 days).
10. Neutral language ("category switching", never "disloyal"); never call a category a "gateway"; transitions are close to independent (chi-square p=${IT.p_value}, Cramer's V=${IT.cramers_v}).
11. Customer recommendations: cite current category, P(B|A), lift, the customer's own rentals in B, weights (${D.settings.w_t}/${D.settings.w_a}) and the movie rule (not rented before, in stock, ranked by popularity).
12. Shoppers: Sakila RENTS DVDs (price per rental), it does not sell them. Categories: ${D.categories.join(", ")}. Missing genres (history, romance): say so and use search_movies with that word as category. Kids/family: only G or PG films.

DATA LIMITATIONS:
${D.limits.map(l => "- " + l.topic + ": " + l.limitation).join("\n")}

Conversation context: ${agentCtx.customer ? `last customer = ${agentCtx.customer}` : "no customer yet"}${agentCtx.category ? `; last category = ${agentCtx.category} (resolve "this category")` : ""}.` +
  (g.length ? "\n\nANSWER GUIDANCE for similar questions from the team's question bank (follow the approach; numbers from tools):\n" + g.map(e => `- Q: ${e.q}\n  How to answer: ${e.guide}\n  Tools: ${e.tools.join(", ") || "none"}`).join("\n") : "");
};

const agentCtx = { customer: null, category: null };
const chat = []; // {role, content, tools?}
const TOOLS = [
  { name: "get_customer_history", description: "Customer profile, rental count and chronological rental journey (titles, categories, dates, repeat/switch flags). Returns the last `max_rentals` rentals.",
    inputSchema: { type: "object", properties: { customer_id: { type: "integer" }, max_rentals: { type: "integer" } }, required: ["customer_id"] },
    run: a => E.customerHistory(+a.customer_id, +(a.max_rentals || 20)) },
  { name: "get_category_transitions", description: "Category transition statistics from all customers' consecutive rentals. direction='outgoing' answers 'where do customers go after X?'; direction='incoming' answers 'which categories lead to X / strongest transition to X?'.",
    inputSchema: { type: "object", properties: { category_name: { type: "string" }, direction: { type: "string", enum: ["outgoing", "incoming"] }, top_n: { type: "integer" } }, required: ["category_name"] },
    run: a => E.categoryProfile(a.category_name, a.direction || "outgoing", +(a.top_n || 5)) },
  { name: "get_customer_recommendation", description: "Data-driven next-category and movie recommendation for a customer, with every input needed to explain it (transition probability, lift, affinity, weights, signal strength, movies).",
    inputSchema: { type: "object", properties: { customer_id: { type: "integer" }, n_movies: { type: "integer" }, exploration_mode: { type: "boolean", description: "true = exclude the customer's current category" } }, required: ["customer_id"] },
    run: a => { const r = E.recommend(+a.customer_id, { nMovies: +(a.n_movies || 5), exploration: !!a.exploration_mode }); r.ranked_categories = r.ranked_categories.slice(0, 5); return r; } },
  { name: "search_movies", description: "Search the Sakila film catalogue (also for shoppers). category accepts a Sakila category OR an everyday genre word like 'history' or 'kids' (mapped to the closest categories, with a genre_note). keyword searches title + description. Returns films with rating, price, popularity, stock and description.",
    inputSchema: { type: "object", properties: { category: { type: "string" }, title: { type: "string" }, keyword: { type: "string", description: "word to find in title or description, e.g. Ancient, Shark" }, rating: { type: "string", enum: ["G", "PG", "PG-13", "R", "NC-17"] }, available_only: { type: "boolean" }, limit: { type: "integer" }, sort_by: { type: "string", enum: ["popularity", "title", "rental_rate", "length"] } } },
    run: a => E.searchMovies(a) },
  { name: "get_insights", description: "The team report's SIX insights recomputed from the database (1 rental-duration policy vs holding time, 2 category loyalty vs switching, 3 DVDs held at checkout/zero state/reactivation, 4 category transitions & lift, 5 hybrid buyers/baskets/price tiers, 6 copies vs rentals productivity). No insight_id = list of six; with insight_id = verified findings, report_check, metrics_to_watch, caveats, hypotheses, follow_up_sql.",
    inputSchema: { type: "object", properties: { insight_id: { type: "integer" } } }, run: a => E.getInsights(a.insight_id) },
  { name: "get_data_limitations", description: "What the Sakila data CANNOT show (chronology gap, visits, demographics, causality, unmet demand, costs/profit, ratings, store attribution, actors, churn, forecasting, BCG). Call before causal/predictive/profit/demographic/churn/market-share/pricing answers.",
    inputSchema: { type: "object", properties: { topic: { type: "string" } } }, run: a => E.dataLimitations(a.topic) },
  { name: "get_trends", description: "Rentals, revenue, active customers by month, quarter or year with the 174-day gap and missing months flagged.",
    inputSchema: { type: "object", properties: { granularity: { type: "string", enum: ["month", "quarter", "year"] } } }, run: a => E.getTrends(a.granularity || "month") },
  { name: "get_business_metrics", description: "Business KPIs and analysis results computed from Sakila. Use key_insights for any insights/summary request (pre-verified). revenue_breakdown = base fees vs late fees; inventory_utilization = copies vs rentals; stores = the 2 branches. metric_name is one of: " + E.METRIC_NAMES.join(", "),
    inputSchema: { type: "object", properties: { metric_name: { type: "string", enum: E.METRIC_NAMES } }, required: ["metric_name"] },
    run: a => E.metric(a.metric_name) },
];
function trackCtx(name, args, res) {
  if (args && args.customer_id) agentCtx.customer = +args.customer_id;
  if (name === "get_customer_recommendation" && res.recommended_category) agentCtx.category = res.recommended_category;
  if (name === "get_category_transitions" && res.category) agentCtx.category = res.category;
}
function callTool(name, args, log) {
  const t = TOOLS.find(x => x.name === name);
  let res;
  try { res = t.run(args || {}); } catch (e) { res = { error: e.message }; }
  trackCtx(name, args, res); log.push({ name, args, res });
  return res;
}

/* grounding check: numbers in an answer must match a number some tool returned */
function unverified(answer, log, q) {
  const DATE = /\b\d{4}-\d{2}(-\d{2})?([ T]\d{2}:\d{2}(:\d{2})?)?\b/g, NUM = /(?<![\w.])-?\$?\d[\d,]*(?:\.\d+)?%?/g;
  const known = new Set([100, 6.25, 16, 1.96]);
  const walk = o => { if (typeof o === "number") known.add(o); else if (typeof o === "string") (o.replace(DATE, " ").match(NUM) || []).forEach(m => known.add(parseFloat(m.replace(/[$,%]/g, ""))));
    else if (o && typeof o === "object") Object.values(o).forEach(walk); };
  log.forEach(c => { walk(c.res); walk(c.args); }); walk(q);
  const cands = []; known.forEach(k => { if (isFinite(k)) cands.push(k, k * 100, k / 100); });
  const bad = new Set();
  (String(answer).replace(DATE, " ").match(NUM) || []).forEach(m => {
    const x = parseFloat(m.replace(/[$,%]/g, "")); if (!isFinite(x)) return;
    if ((Number.isInteger(x) && Math.abs(x) <= 20) || (x >= 1990 && x <= 2030)) return;
    if (!cands.some(k => Math.abs(x - k) <= Math.max(0.0051, 0.005 * Math.abs(k)))) bad.add(m);
  });
  return [...bad];
}

/* markdown-lite renderer for agent answers */
function md(src) {
  const lines = String(src).split("\n"), out = []; let i = 0;
  const inline = s => { const codes = []; let t = esc(s).replace(/`([^`]+)`/g, (_, c) => { codes.push(c); return `\u0000${codes.length - 1}\u0000`; });
    t = t.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/(^|[^*])\*(?!\s)(.+?)\*(?!\*)/g, "$1<i>$2</i>").replace(/(^|\s)_(\S.*?\S|\S)_(?=\s|$|[.,;:])/g, "$1<i>$2</i>");
    return t.replace(/\u0000(\d+)\u0000/g, (_, n) => `<code>${codes[+n]}</code>`); };
  while (i < lines.length) {
    const l = lines[i];
    if (/^\s*```/.test(l)) { const buf = []; i++; while (i < lines.length && !/^\s*```/.test(lines[i])) buf.push(lines[i++]); i++; out.push(`<pre class="sql">${esc(buf.join("\n"))}</pre>`); continue; }
    if (/^\s*\|.*\|\s*$/.test(l) && i + 1 < lines.length && /^\s*\|[\s:|-]+\|\s*$/.test(lines[i + 1])) {
      const cells = r => r.trim().replace(/^\||\|$/g, "").split("|").map(c => c.trim());
      const head = cells(l); i += 2; const rows = [];
      while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) rows.push(cells(lines[i++]));
      out.push(`<div class="tablewrap"><table><thead><tr>${head.map(h => `<th>${inline(h)}</th>`).join("")}</tr></thead><tbody>${rows.map(r => `<tr>${r.map(c => `<td>${inline(c)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`);
      continue;
    }
    if (/^\s*[-*•]\s+/.test(l)) { const items = []; while (i < lines.length && /^\s*[-*•]\s+/.test(lines[i])) items.push(lines[i++].replace(/^\s*[-*•]\s+/, "")); out.push(`<ul>${items.map(x => `<li>${inline(x)}</li>`).join("")}</ul>`); continue; }
    if (/^\s*\d+\.\s+/.test(l)) { const items = []; while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) items.push(lines[i++].replace(/^\s*\d+\.\s+/, "")); out.push(`<ol>${items.map(x => `<li>${inline(x)}</li>`).join("")}</ol>`); continue; }
    if (/^#{1,4}\s+/.test(l)) { out.push(`<p><b>${inline(l.replace(/^#+\s+/, ""))}</b></p>`); i++; continue; }
    if (l.trim()) out.push(`<p>${inline(l)}</p>`);
    i++;
  }
  return out.join("");
}

/* offline router: same tools, template answers (used when the Claude capability is unavailable) */

/* ---------- broader offline understanding (English + Vietnamese), used before the fixed router ---------- */
const strip = t => t.normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/g, "d").replace(/Đ/g, "D").toLowerCase();
const VI_GENRE = { "hanh dong": "Action", "hoat hinh": "Animation", "tre em": "kids", "thieu nhi": "kids", "kinh dien": "Classics", "hai huoc": "Comedy", "phim hai": "Comedy",
  "tai lieu": "Documentary", "chinh kich": "Drama", "tam ly": "Drama", "gia dinh": "Family", "nuoc ngoai": "Foreign", "tro choi": "Games", "kinh di": "Horror",
  "am nhac": "Music", "ca nhac": "Music", "khoa hoc vien tuong": "Sci-Fi", "vien tuong": "Sci-Fi", "the thao": "Sports", "du lich": "Travel", "lich su": "history",
  "lang man": "romance", "tinh cam": "romance", "chien tranh": "war" };
const MONTHS = { jan: 1, feb: 2, mar: 3, apr: 4, may: 5, jun: 6, jul: 7, aug: 8, sep: 9, oct: 10, nov: 11, dec: 12 };
const GLOSSARY = [
  [/\b(income|revenue|doanh thu|thu nhap|earning|sales)\b/, "income",
    ["**Income / revenue** in this project = the sum of `payment.amount`, the money customers paid for rentals (plus late fees when a DVD is returned late). Sakila rents DVDs, it does not sell them.",
     "**Income / doanh thu** trong dự án = tổng `payment.amount`, tức số tiền khách trả khi thuê đĩa (gồm cả phí trả trễ). Sakila cho thuê DVD, không bán đĩa."]],
  [/\blift\b/, "lift", ["**Lift** = P(B | A) ÷ B's overall share. Lift 1 = exactly as often as expected by chance; above 1 = more often.", "**Lift** = P(B | A) ÷ tỷ trọng chung của B. Lift = 1 nghĩa là đúng như ngẫu nhiên; lớn hơn 1 là thường xuyên hơn mức ngẫu nhiên."]],
  [/\b(transition|chuyen doi|chuyen the loai)\b/, "transition", ["A **category transition** A → B = a customer's rental in category A followed by their next rental in category B (rentals sorted by rental_date, rental_id).", "**Category transition** A → B = khách thuê một phim thể loại A và lần thuê kế tiếp là thể loại B (sắp theo rental_date, rental_id)."]],
  [/\bgateway\b/, "gateway", null],
  [/\b(cramer|p.?value|chi.?square|chi2|y nghia thong ke)\b/, "stats", ["The **chi-square test** checks whether the next category depends on the previous one; **p** < 0.05 would mean a real dependence. **Cramér's V** measures strength (below 0.1 = negligible).", "**Kiểm định chi-square** xem thể loại kế tiếp có phụ thuộc thể loại trước không; **p** < 0,05 mới là có phụ thuộc thật. **Cramér's V** đo độ mạnh (dưới 0,1 = không đáng kể)."]],
  [/\b(affinity)\b/, "affinity", ["**Affinity** = the customer's own smoothed share of a category: (rentals in B + 1) ÷ (total rentals + 16).", "**Affinity** = tỷ trọng (đã làm trơn) của thể loại trong lịch sử của chính khách: (số lần thuê B + 1) ÷ (tổng lượt thuê + 16)."]],
];
function offlinePlus(q, log) {
  const s = strip(q), vi = /[À-ỹ]/.test(q) || /\b(la gi|bao nhieu|khach|doanh thu|thu nhap|phim|the loai|nam|thang|nhieu nhat)\b/.test(s);
  const T = (en, v) => vi ? v : en;
  const yr = (s.match(/\b(20\d\d)\b/) || [])[1];
  let mon = null; for (const [k, v] of Object.entries(MONTHS)) if (new RegExp(`\\b${k}[a-z]*\\b`).test(s)) mon = v;
  const tm = s.match(/thang\s*(\d{1,2})/); if (tm) mon = +tm[1];
  const W = D.outside_window || {};
  const isDef = /\b(la gi|what is|what does|what are|define|meaning|nghia la|y nghia)\b/.test(s);
  // 1) "what is X" glossary
  if (isDef) for (const [re, key, txt] of GLOSSARY) if (re.test(s)) {
    if (key === "gateway") return null;
    let out = txt[vi ? 1 : 0];
    if (key === "income") { const v = callTool("get_business_metrics", { metric_name: "total_revenue" }, log).value;
      out += T(`\n\nIn the analysis window (${H.first_rental.slice(0, 10)} → ${H.last_rental.slice(0, 10)}), Sakila's income was **${money(v.total_revenue)}**.`, `\n\nTrong giai đoạn phân tích (${H.first_rental.slice(0, 10)} → ${H.last_rental.slice(0, 10)}), doanh thu của Sakila là **${money(v.total_revenue)}**.`); }
    return out;
  }
  // 2) income / revenue with optional year / month
  if (/\b(income|revenue|doanh thu|thu nhap|earning|earnings|sales|tien)\b/.test(s) && !/\bcategor|the loai\b/.test(s)) {
    const m = callTool("get_business_metrics", { metric_name: "rental_trends" }, log).value;
    if (yr && yr !== "2005") {
      return yr === "2006" ? T(`The analysis window ends before ${D.settings.end}. Outside it, Sakila recorded one batch on ${W.first_date}: **${W.rentals} rentals** and **${money(W.revenue)}** in payments (excluded from the analysis as anomalous, following the team's SQL). All-time income is ${money(W.all_time_revenue)}.`,
        `Giai đoạn phân tích kết thúc trước ${D.settings.end}. Ngoài giai đoạn này chỉ có một đợt ngày ${W.first_date}: **${W.rentals} lượt thuê**, **${money(W.revenue)}** thanh toán (bị loại vì bất thường, theo SQL của nhóm). Tổng doanh thu mọi thời điểm là ${money(W.all_time_revenue)}.`)
        : T(`Sakila has no data for ${yr}. Rentals run from ${H.first_rental.slice(0, 10)} to ${W.first_date || H.last_rental.slice(0, 10)}.`, `Sakila không có dữ liệu năm ${yr}. Dữ liệu thuê chạy từ ${H.first_rental.slice(0, 10)} đến ${W.first_date || H.last_rental.slice(0, 10)}.`);
    }
    const rows = mon ? m.filter(r => +r.month.slice(5) === mon) : m;
    if (mon && !rows.length) return T(`No rentals were recorded in month ${mon} of 2005. Months with data: ${m.map(r => r.month).join(", ")}.`, `Không có giao dịch trong tháng ${mon}/2005. Các tháng có dữ liệu: ${m.map(r => r.month).join(", ")}.`);
    const tot = rows.reduce((a, r) => a + r.revenue, 0);
    return T(`**Sakila income${mon ? ` in ${rows[0].month}` : " in 2005"}: ${money(tot)}**`, `**Doanh thu Sakila${mon ? ` tháng ${+rows[0].month.slice(5)}/2005` : " năm 2005"}: ${money(tot)}**`) +
      `\n\n| ${T("Month", "Tháng")} | ${T("Income", "Doanh thu")} | ${T("Rentals", "Lượt thuê")} | ${T("Active customers", "Khách hoạt động")} |\n|---|---|---|---|\n` +
      rows.map(r => `| ${r.month} | ${money(r.revenue)} | ${fmt(r.rentals)} | ${fmt(r.active_customers)} |`).join("\n") +
      T(`\n\n_Income = sum of payments. Sakila only has rentals from ${H.first_rental.slice(0, 10)}; the window excludes the ${W.rentals}-rental batch on ${W.first_date}._`, `\n\n_Doanh thu = tổng các khoản thanh toán. Dữ liệu bắt đầu từ ${H.first_rental.slice(0, 10)}; đã loại đợt ${W.rentals} lượt thuê ngày ${W.first_date}._`);
  }
  // 2a) team insights, SQL, metrics, report, trends, personas, limits
  if (/\bsql\b|query|truy van/.test(s) && /insight/.test(s)) {
    const xs = [1, 2, 3, 4, 5, 6].map(i => callTool("get_insights", { insight_id: i }, log));
    return T("Follow-up SQL for each insight:", "SQL tiếp theo cho từng insight:") + "\n\n" + xs.map(x => `**Insight ${x.id} - ${x.title}**\n\n\`\`\`sql\n${x.follow_up_sql}\n\`\`\``).join("\n\n");
  }
  if (/\b(metrics?|kpis?|chi so)\b/.test(s) && !/revenue|doanh thu/.test(s)) {
    const xs = [1, 2, 3, 4, 5, 6].map(i => callTool("get_insights", { insight_id: i }, log));
    return T("Metrics to watch, by insight:", "Các chỉ số cần theo dõi theo từng insight:") + "\n\n" + xs.map(x => `- **Insight ${x.id}**: ` + Object.entries(x.metrics_to_watch).map(([k, v]) => `\`${k}\` = ${v}`).join("; ")).join("\n");
  }
  if (/\b(visuali[sz]e|chart|graph|bieu do)\b/.test(s)) return T("Charts for the analysis are on the dashboard tabs: **1 Overview** (monthly, daily, categories), **2 Customer exploration** (repeat vs chance, diversity, discovery curve), **3 Category transition** (heatmap, top transitions, gateway test), **4 Recommendation** (score breakdown, hold-out test). The Streamlit version renders insight 1-6 charts inside the chat.", "Biểu đồ nằm ở các tab dashboard: **1 Overview**, **2 Customer exploration**, **3 Category transition**, **4 Recommendation**. Bản Streamlit vẽ biểu đồ insight 1-6 ngay trong khung chat.");
  if (/\b(report|story|memo|bao cao|cau chuyen)\b/.test(s)) {
    const a = callTool("get_insights", {}, log), lim = callTool("get_data_limitations", {}, log).limitations;
    return "# Sakila retains every customer, but its policies and assortment are not tuned to how customers actually behave\n\n**Executive summary**\n- *Situation*: all 599 customers return and rent across most categories.\n- *Complication*: due dates, prices and inventory are set per title, while behaviour is uniform (about 5 days held on average under every policy; demand spread evenly).\n- *Resolution*: test policy changes (extension option, bundles, copy reallocation) with controlled pilots.\n\n**Key findings**\n" +
      a.insights.map(x => `${x.id}. **${x.title}** - ${x.verified_findings.slice(0, 2).join(" ")}`).join("\n") +
      "\n\n**Recommendations (to be tested)**\n1. Pre-due-date extension option priced below the late fee (pilot one store).\n2. Two-title same-category bundle for single-$0.99 visits (A/B test).\n3. Next-title suggestions when a customer is down to one open DVD.\n4. Review copies for high/low rentals-per-copy films.\n\n**Risks & data limitations**\n" + lim.slice(0, 5).map(l => `- ${l.limitation}`).join("\n") + "\n\n**Next steps**: 30 days define KPIs and control groups; 60 days run pilots; 90 days read results and decide.";
  }
  if (/\b(forecast|predict|du bao|bcg|combo|bulk|elasticit|profit|loi nhuan|lucas|churn|lifetime|gender|gioi tinh|age group|do tuoi)\b/.test(s)) {
    const topic = /forecast|predict|du bao/.test(s) ? "forecast" : /bcg/.test(s) ? "bcg" : /profit|loi nhuan/.test(s) ? "money" : /churn|lifetime/.test(s) ? "churn" : /gender|gioi tinh|age|do tuoi/.test(s) ? "demographics" : "causality";
    const lim = callTool("get_data_limitations", { topic }, log).limitations;
    const extra = topic === "causality" ? "\n\n" + callTool("get_insights", { insight_id: 5 }, log).recommendations_hypotheses[0] : "";
    return T("What the data can and cannot show here:", "Dữ liệu có thể và không thể cho thấy gì:") + "\n\n" + lim.map(l => `- ${l.limitation}`).join("\n") + extra;
  }
  if (/\b(trend|monthly|quarter|quarterly|yearly|annual|xu huong|theo quy|theo nam)\b/.test(s)) {
    const g = /quarter|quy/.test(s) ? "quarter" : /year|annual|nam\b/.test(s) ? "year" : "month", t = callTool("get_trends", { granularity: g }, log);
    return `| Period | Rentals | Revenue | Recorded days |\n|---|---|---|---|\n` + t.rows.map(r => `| ${r.period} | ${fmt(r.rentals)} | ${money(r.revenue)} | ${r.recorded_days} |`).join("\n") + `\n\n**${T("Warning", "Lưu ý")}:** ${t.warning}`;
  }
  if (/\b(persona|segment|phan khuc|chan dung)\b/.test(s)) {
    const v = callTool("get_business_metrics", { metric_name: "customer_segments" }, log).value;
    return v.method + "\n\n| Segment | Customers | Avg rentals | Avg revenue | Late share |\n|---|---|---|---|---|\n" + v.segments.map(r => `| ${r.segment} | ${r.customers} | ${r.avg_rentals} | $${r.avg_revenue} | ${r.avg_late_share_pct}% |`).join("\n") + `\n\n_${v.caveat}_`;
  }
  if (/\b(insights?|findings?|summary|summarize|tom tat|phat hien)\b/.test(s)) {
    const a = callTool("get_insights", {}, log);
    return T(`There are **${a.count} insights** (recomputed from the database):`, `Có **${a.count} insight** (tính lại từ database):`) + "\n\n" + a.insights.map(x => `${x.id}. **${x.title}** - ${x.verified_findings[0]}`).join("\n");
  }
  // 2b) stores / branches
  if (/\b(stores?|shops?|branch(es)?|chi nhanh|cua hang)\b/.test(s)) {
    const v = callTool("get_business_metrics", { metric_name: "stores" }, log).value;
    return T(`Sakila has **${v.total_stores} stores**:`, `Sakila có **${v.total_stores} cửa hàng (chi nhánh)**:`) +
      `\n\n| ${T("Store", "Cửa hàng")} | ${T("Location", "Địa điểm")} | ${T("Manager", "Quản lý")} | ${T("Customers", "Khách hàng")} | ${T("Copies", "Số đĩa")} | ${T("Rentals", "Lượt thuê")} | ${T("Revenue", "Doanh thu")} |\n|---|---|---|---|---|---|---|\n` +
      v.stores.map(r => `| ${r.store_id} | ${r.city}, ${r.country} | ${r.manager} | ${r.customers} | ${fmt(r.copies)} | ${fmt(r.rentals)} | ${money(r.revenue)} |`).join("\n") +
      T("\n\n_Rentals and revenue are attributed to the store that owns the rented copy._", "\n\n_Lượt thuê và doanh thu được tính cho cửa hàng sở hữu đĩa được thuê._");
  }
  // 3) counts
  if (/\b(how many|bao nhieu|number of|so luong|tong so)\b/.test(s)) {
    const v = callTool("get_business_metrics", { metric_name: "overview" }, log).value;
    if (/customer|khach/.test(s)) return T(`Sakila has **${v.total_customers} customers**, all of whom rented in the analysis window.`, `Sakila có **${v.total_customers} khách hàng**, tất cả đều có thuê trong giai đoạn phân tích.`);
    if (/film|movie|phim|title/.test(s)) return T(`The catalogue has **${fmt(v.total_films)} films** and **${fmt(v.total_copies)} physical copies**.`, `Danh mục có **${fmt(v.total_films)} phim** và **${fmt(v.total_copies)} bản đĩa**.`);
    if (/rental|thue|order|giao dich/.test(s)) return T(`**${fmt(v.total_rentals)} rentals** in the analysis window.`, `**${fmt(v.total_rentals)} lượt thuê** trong giai đoạn phân tích.`);
    if (/categor|the loai/.test(s)) return T(`There are **${D.categories.length} categories**: ${D.categories.join(", ")}.`, `Có **${D.categories.length} thể loại**: ${D.categories.join(", ")}.`);
  }
  // 4) most popular films
  if (/\b(most (rented|popular)|top|best|pho bien|thue nhieu nhat|hot nhat)\b/.test(s) && /\b(film|movie|phim|title|dvd)\b/.test(s)) {
    const vg = Object.keys(VI_GENRE).find(k => s.includes(k)); const c = D.categories.find(x => new RegExp(`\\b${x.toLowerCase()}\\b`).test(s)) || (vg && VI_GENRE[vg]);
    const r = callTool("search_movies", { ...(c ? { category: c } : {}), limit: 5, sort_by: "popularity" }, log);
    if (r.error) return r.error;
    return T(`Most rented ${c ? c + " " : ""}films in the analysis window:`, `Phim ${c ? c + " " : ""}được thuê nhiều nhất trong giai đoạn phân tích:`) + "\n\n" +
      r.movies.map((m, i) => `${i + 1}. **${title(m.title)}** (${m.category}, ${m.rating}): ${m.rentals_in_window} ${T("rentals", "lượt thuê")}`).join("\n") + (r.genre_note ? `\n\n_${r.genre_note}_` : "");
  }
  // 5) "sakila la gi" / about
  if (/\b(sakila)\b/.test(s) && (isDef || /\babout\b|gioi thieu/.test(s))) {
    const v = callTool("get_business_metrics", { metric_name: "overview" }, log).value;
    return T(`**Sakila** is a sample database of a DVD rental chain (2 stores). In the analysis window it has ${v.total_customers} customers, ${fmt(v.total_films)} films in ${D.categories.length} categories, ${fmt(v.total_rentals)} rentals and ${money(v.total_revenue)} in income.`,
      `**Sakila** là cơ sở dữ liệu mẫu của một chuỗi cho thuê DVD (2 cửa hàng). Trong giai đoạn phân tích có ${v.total_customers} khách hàng, ${fmt(v.total_films)} phim thuộc ${D.categories.length} thể loại, ${fmt(v.total_rentals)} lượt thuê và doanh thu ${money(v.total_revenue)}.`);
  }
  // 6) Vietnamese genre shopping ("muốn thuê phim kinh dị", "phim cho trẻ em")
  const vg = Object.keys(VI_GENRE).sort((a, b) => b.length - a.length).find(k => s.includes(k));
  if (vg && /\b(phim|dvd|thue|mua|xem|goi y)\b/.test(s)) {
    const r = callTool("search_movies", { category: VI_GENRE[vg], available_only: true, limit: 5 }, log);
    if (r.error) return r.error;
    const buy = /\bmua\b/.test(s) ? "Sakila **cho thuê** DVD chứ không bán đĩa. " : "";
    const note = r.genre_note ? r.genre_note.replace(/^Sakila has no '(.+?)' category\. Closest categories: (.+?)(;|\.)/, (_, a, b) => `Sakila không có thể loại "${a}". Thể loại gần nhất: ${b}.`).replace("Only G and PG rated films are shown for a family/kids request.", "Chỉ hiển thị phim rating G và PG cho trẻ em.") : `Phim ${VI_GENRE[vg]} còn hàng, được thuê nhiều nhất:`;
    return `Chào bạn! ${buy}${note}\n\n${r.movies.map(m => `- **${title(m.title)}** (${m.category}, ${m.rating}, $${m.rental_rate}/lượt thuê): ${m.available_copies} đĩa còn trong kho`).join("\n")}`;
  }
  return null;
}

function offline(q, log) {
  const pre = offlinePlus(q, log); if (pre) return pre;
  const ql = q.toLowerCase(), words = { one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10 };
  const m = ql.match(/customer\s*(?:id)?\s*#?\s*(\d{1,3})/); if (m) agentCtx.customer = +m[1];
  const explicit = !!m, cid = agentCtx.customer;
  let cat = null; for (const c of [...D.categories].sort((a, b) => b.length - a.length)) if (new RegExp(`\\b${c.replace("-", "\\-")}\\b`, "i").test(q)) { cat = c; break; }
  if (!cat && /\b(this|that) category\b/.test(ql)) cat = agentCtx.category;
  const nm = ql.match(new RegExp(`\\b(\\d{1,2}|${Object.keys(words).join("|")})\\s+(?:\\w+\\s+)?(?:movies|films|titles)`)); const nMovies = nm ? (words[nm[1]] || +nm[1]) : 5;
  const refers = explicit || /\b(this|that) customer\b|\b(they|their|them|he|she|his|her)\b/.test(ql);
  const reco = (args, explain) => { const r = callTool("get_customer_recommendation", args, log); if (r.error) return r.error;
    return `**Customer ${r.customer_id} (${r.customer_name}) → recommended category: ${r.recommended_category}** (signal: ${r.signal_strength})\n\nRecent categories: ${r.recent_categories.join(" → ")}\n\n**Why:** the most recent rental was **${r.current_category}**. Across all Sakila rental sequences, ${r.transitions_observed} of ${r.outgoing_transitions_from_current} transitions out of ${r.current_category} went to ${r.recommended_category} (P = ${pct(r.transition_probability)}, lift ${r.lift_vs_baseline}). The customer has rented ${r.customer_rentals_in_recommended_category} ${r.recommended_category} film(s) of ${r.rentals_in_window}. Score = ${r.weights.transition}×transition + ${r.weights.affinity}×affinity = ${r.score}.\n\n` +
      (explain ? `Top categories: ${r.ranked_categories.slice(0, 3).map(c => `${c.category} (${c.score.toFixed(4)})`).join(", ")}\n\n` : "") +
      `**Movies** (never rented by this customer, in stock, ranked by popularity):\n${r.recommended_movies.map(x => `- **${title(x.title)}** (${x.rating}, $${x.rental_rate}): ${x.rentals_in_window} rentals, ${x.available_copies} in stock`).join("\n")}\n\n_Caveat: overall, the next category is close to independent of the previous one (χ² p = ${r.global_signal.chi2_p_value}), so treat this as a suggestion informed by the data, not a prediction._`; };
  if (cid && /\bwhy\b|explain|reason/.test(ql) && /recommend|categor|suggest|movie|film/.test(ql)) return reco({ customer_id: cid }, true);
  if (!explicit && /significan|random|chi.?square|independen|predictab/.test(ql)) { const v = callTool("get_business_metrics", { metric_name: "transition_statistics" }, log).value;
    return `${v.interpretation}\n\n- χ² = ${v.chi2} (dof ${v.dof}), p = ${v.p_value}\n- Cramér's V = ${v.cramers_v}\n- Highest P(B|A) = ${pct(v.max_probability)} vs chance ${pct(v.uniform_probability)}\n- Cells significant after Bonferroni: ${v.cells_significant_after_bonferroni} of ${v.cells}`; }
  if (/backtest|accura|hit rate|evaluat/.test(ql)) { const v = callTool("get_business_metrics", { metric_name: "recommendation_backtest" }, log).value;
    return `Hold-out test (each customer's last rental hidden):\n\n| Method | hit@1 | hit@3 |\n|---|---|---|\n| Random | ${v["random_hit@1_pct"]}% | ${v["random_hit@3_pct"]}% |\n| Popularity | ${v["popularity_hit@1_pct"]}% | ${v["popularity_hit@3_pct"]}% |\n| Transition only | ${v["transition_only_hit@1_pct"]}% | ${v["transition_only_hit@3_pct"]}% |\n| App blend | ${v["app_blend_hit@1_pct"]}% | ${v["app_blend_hit@3_pct"]}% |\n\nStandard error ≈ ±${v["standard_error_hit@3_pp"]} pp, so the differences are within noise.`; }
  if (cid && (refers || /recommend|watch next|suggest/.test(ql)) && /recommend|watch next|suggest|should .* watch|next category/.test(ql)) return reco({ customer_id: cid, n_movies: nMovies, exploration_mode: /explor|new category|different category/.test(ql) });
  if (cid && refers && /journey|history|rented|profile|rentals/.test(ql)) { const r = callTool("get_customer_history", { customer_id: cid, max_rentals: 12 }, log); if (r.error) return r.error;
    return `**${r.customer.name}** (customer ${r.customer.customer_id}, ${r.customer.location}): ${r.rental_count} rentals across ${r.distinct_categories} categories, with ${r.switch_transitions} switches and ${r.repeat_transitions} repeats.\n\nJourney: ${r.category_journey.replace(/ -> /g, " → ")}\n\n| # | Date | Title | Category | Step |\n|---|---|---|---|---|\n${r.rentals.map(x => `| ${x.rental_number} | ${x.rental_date.slice(0, 10)} | ${title(x.title)} | ${x.category} | ${x.transition} |`).join("\n")}`; }
  const trans = dir => { const r = callTool("get_category_transitions", { category_name: cat, direction: dir }, log); if (r.error) return r.error;
    const foot = `\n\n_Chance level is 6.25%; overall χ² p = ${r.statistical_context.p_value} and Cramér's V = ${r.statistical_context.cramers_v}. These differences are small and mostly within random variation._`;
    if (dir === "incoming") return `Categories whose customers most often move **into ${r.category}** next:\n\n| From | Transitions | P(${r.category} given from) | Lift | z |\n|---|---|---|---|---|\n${r.top_source_categories.map(x => `| ${x.from_category} | ${x.transitions} | ${pct(x.probability_from_source)} | ${x.lift} | ${x.z_residual} |`).join("\n")}` + foot;
    return `After renting **${r.category}** (${r.outgoing_transitions} observed next rentals), customers most often move to:\n\n| Next category | Transitions | Probability | Lift | z |\n|---|---|---|---|---|\n${r.top_destinations.map(x => `| ${x.to_category} | ${x.transitions} | ${pct(x.probability)} | ${x.lift} | ${x.z_residual} |`).join("\n")}\n\nThey rent ${r.category} again ${pct(r.self_transition_probability)} of the time, and all ${r.unique_destination_categories} other categories are reached.` + foot; };
  const shop = /\b(want|looking for|buy|rent|find|any|suggest|recommend me|in the mood|show me|need)\b/.test(ql) && /movie|film|dvd|something|watch/.test(ql) && !explicit;
  if (shop) {
    const syn = D.genre ? Object.keys(D.genre.synonyms).sort((a, b) => b.length - a.length) : [];
    const word = cat || syn.find(k => new RegExp(`\\b${k}\\b`).test(ql));
    const r = callTool("search_movies", word ? { category: word, available_only: true, limit: nMovies } : { available_only: true, limit: nMovies }, log);
    if (r.error) return r.error;
    const buy = /\b(buy|purchase)\b/.test(ql) ? "Just so you know: Sakila **rents** DVDs rather than selling them. " : "";
    const head = r.genre_note || (word ? `Top available ${word} films:` : "Here are our most popular films in stock right now:");
    return `Hi! ${buy}${head}\n\n${r.movies.map(m => `- **${title(m.title)}** (${m.category}, ${m.rating}, $${m.rental_rate} per rental): ${m.description}. ${m.available_copies} copies in stock`).join("\n")}`;
  }
  if (cat && /strongest transition to|lead(s)? to|into|before|come from|towards?/.test(ql)) return trans("incoming");
  if (cat && /next|after|go|move|transition|switch/.test(ql)) return trans("outgoing");
  if (/gateway|high.transition/.test(ql)) { const v = callTool("get_business_metrics", { metric_name: "high_transition_categories" }, log).value;
    return `**Is a gateway supported by the data? No.** The app uses the term *${v.assessment.label_used}* instead.\n\n${v.assessment.explanation}\n\n${v.table.slice(0, 3).map(t => `- ${t.category}: ${t.outgoing_transitions} outgoing transitions, entropy ${t.outgoing_entropy}, strongest → ${t.strongest_destination} (${pct(t.strongest_probability)})`).join("\n")}`; }
  if (/switch|repeat|loyal|explor|same category/.test(ql)) { const v = callTool("get_business_metrics", { metric_name: "repeat_vs_switch" }, log).value;
    return `Of ${fmt(v.transitions)} consecutive-rental pairs, **${v.switch_pct}% switch category** and ${v.repeat_pct}% repeat it. Pure chance would give about ${v.random_choice_repeat_pct}% repeats (shuffled sequences: ${v.shuffled_sequence_repeat_pct}%, p = ${v.shuffled_repeat_p_value}), so repetition is only slightly above chance.`; }
  if (/(most|top).*(rented|popular).*categor|categor.*(most|popular)/.test(ql)) { const v = callTool("get_business_metrics", { metric_name: "most_rented_categories" }, log).value;
    return `Most rented categories:\n\n| Category | Rentals | Share |\n|---|---|---|\n${v.slice(0, 8).map(r => `| ${r.category} | ${fmt(r.rentals)} | ${r.rental_share_pct.toFixed(2)}% |`).join("\n")}`; }
  if (/revenue/.test(ql) && /categor/.test(ql)) { const v = callTool("get_business_metrics", { metric_name: "category_revenue" }, log).value;
    return `Revenue by category:\n\n| Category | Revenue | Share |\n|---|---|---|\n${v.slice(0, 8).map(r => `| ${r.category} | ${money(r.revenue)} | ${r.revenue_share_pct.toFixed(2)}% |`).join("\n")}`; }
  if (cat && /movie|film|title/.test(ql)) { const v = callTool("search_movies", { category: cat, available_only: true, limit: nMovies }, log);
    return `Top available ${cat} films by rentals:\n\n${v.movies.map(x => `- **${title(x.title)}** (${x.rating}, $${x.rental_rate}): ${x.rentals_in_window} rentals, ${x.available_copies} in stock`).join("\n")}`; }
  if (/revenue|customers|rentals|kpi|overview|rate/.test(ql)) { const v = callTool("get_business_metrics", { metric_name: "overview" }, log).value;
    return `- Customers: ${v.total_customers}\n- Rentals: ${fmt(v.total_rentals)}\n- Revenue: ${money(v.total_revenue)}\n- Avg catalogue rental rate: ${money(v.avg_catalog_rental_rate)}\n- Most rented category: ${v.most_rented_category} (${fmt(v.most_rented_category_rentals)} rentals)`; }
  const vi = /[\u00C0-\u1EF9]/.test(q);
  return vi ? "Mình chưa hiểu câu này ở **chế độ offline** (Claude chưa được bật ở trang này). Bạn có thể hỏi về:\n\n- **Doanh thu**: *doanh thu năm 2005*, *doanh thu tháng 7*\n- **Số lượng**: *có bao nhiêu khách hàng / phim / lượt thuê*\n- **Phim**: *phim được thuê nhiều nhất*, *muốn thuê phim kinh dị*, *phim cho trẻ em*\n- **Khách hàng**: *khách 42 nên xem gì tiếp*, *hành trình thuê của customer 42*\n- **Thể loại**: *Where do Action customers go next?*, *thể loại nào được thuê nhiều nhất*\n- **Định nghĩa**: *lift là gì*, *income là gì*, *Cramér's V là gì*"
    : "I didn't catch that in **offline mode** (Claude isn't enabled on this page). Try one of these topics:\n\n- **Income**: *income in 2005*, *revenue in July*\n- **Counts**: *how many customers / films / rentals*\n- **Films**: *most rented films*, *any scary movies?*, *films for my kids*\n- **Customers**: *What should customer 42 watch next?*, *Show me customer 42's rental journey*\n- **Categories**: *Where do Action customers go next?*, *most rented categories*, *Is there a gateway category?*\n- **Definitions**: *what is lift*, *what is income*, *what is Cramér's V*";
}

let sampleFn = null, sampleChecked = false, sampleWithTools = false, busyCtl = null;
async function initSample() {
  try {
    if (window.claude && window.claude.use) {
      sampleFn = await window.claude.use("sample");
      if (sampleFn) { const lim = await sampleFn.limits().catch(() => null); sampleWithTools = !!(lim && lim.tools); }
    }
  } catch (e) { sampleFn = null; }
  sampleChecked = true; paintStatus();
}
function paintStatus() {
  const el = $("#agentstatus"); if (!el) return;
  el.innerHTML = !sampleChecked ? `<span class="dot"></span>Checking whether Claude is available…`
    : sampleFn ? `<span class="dot on"></span>Live mode: Claude ${sampleWithTools ? "calls" : "plans, then the page runs"} the 5 Sakila tools and answers any question in your own words (runs on your Claude account; asks for permission the first time)`
    : `<span class="dot"></span>Offline mode: a fixed router calls the same tools and fills answer templates (Claude isn't available in this view)`;
}
PAGES.agent = () => {
  if (lastReco && (lastReco.customer_id !== agentCtx.syncedC || lastReco.category !== agentCtx.syncedK)) {
    agentCtx.customer = lastReco.customer_id; agentCtx.category = lastReco.category; agentCtx.syncedC = lastReco.customer_id; agentCtx.syncedK = lastReco.category;
  }
  const c = agentCtx.customer || 42;
  const ex = [`What should customer ${c} watch next?`, "Why did you recommend this category?", "Which categories do customers most often move to after this category?",
    `Show me customer ${c}'s rental journey`, "Which category has the strongest transition to Comedy?", "Is the next category predictable, or close to random?", "Is there a gateway category?", "What are the most rented categories?", "Hi, I want to rent a history DVD", "Something funny and short for tonight?", "Any good films for my kids?"];
  return `<div><div class="kicker">Step 5</div><h1>Sakila AI business agent</h1>
    <p class="lede">Ask about customer behaviour, category transitions, recommendations, movies or business metrics. The agent answers by calling tools that query the Sakila data. Open "tools used" under an answer to see the exact data behind it.</p></div>
    <div class="status" id="agentstatus"></div>
    <div class="examples">${ex.map(q => `<button type="button" data-q="${esc(q)}">${esc(q)}</button>`).join("")}</div>
    <div class="chat" id="chat" aria-live="polite"></div>
    <form class="composer" id="composer"><label for="qbox" class="field" style="flex:1">Your question<textarea id="qbox" rows="2" placeholder="e.g. Where do Horror customers usually go next?"></textarea></label>
      <button class="btn" id="send" type="submit">Ask</button><button class="btn ghost" id="stop" type="button" hidden>Stop</button>
      <button class="btn ghost" id="clear" type="button">Clear</button></form>
    <p class="lede" style="font-size:12.5px">Tools: get_customer_history · get_category_transitions · get_customer_recommendation · search_movies · get_business_metrics.</p>`;
};
draws.push(["agent", () => { paintStatus(); paintChat(); }]);
function paintChat() {
  const el = $("#chat"); if (!el) return;
  if (!chat.length) { el.innerHTML = `<p class="lede" style="font-size:14px">No questions yet. Pick an example above or type your own.</p>`; return; }
  el.innerHTML = chat.map(m => `<div class="msg ${m.role === "user" ? "user" : "bot"}"><span class="who">${m.role === "user" ? "You" : "AI"}</span><div class="body">${m.role === "user" ? esc(m.content) : (m.pending ? `<p class="thinking">${esc(m.pending)}</p>` : md(m.content))}
    ${m.tools && m.tools.length ? `<div class="toolrun">${m.tools.map(t => `<details><summary>tool used · ${esc(t.name)}(${esc(JSON.stringify(t.args))})</summary><pre>${esc(JSON.stringify(t.res, null, 1).slice(0, 6000))}</pre></details>`).join("")}</div>` : ""}
    ${m.unverified && m.unverified.length ? `<div class="note caution" style="margin-top:6px;font-size:13px"><b class="tag">Grounding check</b>These numbers could not be matched to any tool result: ${esc(m.unverified.join(", "))}. Treat them with caution.</div>` : ""}
    ${m.mode ? `<div class="status">${esc(m.mode)}</div>` : ""}</div></div>`).join("");
  el.lastElementChild && el.lastElementChild.scrollIntoView({ block: "nearest" });
}
async function ask(q) {
  q = q.trim(); if (!q || busyCtl) return;
  const log = [];
  chat.push({ role: "user", content: q });
  const bot = { role: "assistant", content: "", tools: log, pending: "Thinking…" }; chat.push(bot); paintChat();
  const m = q.match(/customer\s*(?:id)?\s*#?\s*(\d{1,3})/i); if (m) agentCtx.customer = +m[1];
  if (!sampleFn) { bot.content = offline(q, log); bot.pending = null; bot.mode = "offline mode · answer built from tool results"; paintChat(); return; }
  busyCtl = new AbortController(); $("#stop").hidden = false; $("#send").disabled = true;
  const turns = chat.filter(x => x !== bot && !x.pending && x.content).slice(-8).map(x => ({ role: x.role, content: x.content }));
  try {
    if (!sampleWithTools) {
      /* Plan -> execute -> answer: the same agent loop, with the tool choice returned as JSON */
      const catalog = TOOLS.map(t => `- ${t.name}: ${t.description} Args schema: ${JSON.stringify(t.inputSchema.properties)}`).join("\n");
      const convo = turns.map(t => `${t.role.toUpperCase()}: ${t.content.slice(0, 1500)}`).join("\n");
      bot.pending = "Choosing which Sakila data to look up…"; paintChat();
      const plan = await sampleFn.json(`You route questions for the Sakila DVD rental AI agent. Pick the tool calls (0-4) needed to answer the LAST user message with real data.
Tools:\n${catalog}\n
Context: last customer discussed = ${agentCtx.customer || "none"}; last category discussed/recommended = ${agentCtx.category || "none"} (resolve "this category"/"they" with these).
Conversation:\n${convo}\n
Reply with only JSON: {"calls":[{"tool":"<name>","args":{...}}]}. Use [] only for pure small talk.`, { modelTier: "quick", cache: false, signal: busyCtl.signal });
      const calls = (plan && Array.isArray(plan.calls) ? plan.calls : []).slice(0, 4);
      const results = calls.filter(c => TOOLS.some(t => t.name === c.tool)).map(c => { bot.pending = `Querying Sakila: ${c.tool}…`; paintChat(); return { tool: c.tool, args: c.args || {}, result: callTool(c.tool, c.args || {}, log) }; });
      const data = JSON.stringify(results).slice(0, 40000);
      const { text } = await sampleFn([{ role: "user", content: RULES(q) }, ...turns.slice(0, -1),
        { role: "user", content: `${q}\n\n[TOOL RESULTS from the Sakila database, the only source you may use for facts]\n${data}` }],
        { cache: false, signal: busyCtl.signal, onText: ({ text }) => { bot.pending = null; bot.content = text; paintChat(); } });
      bot.content = text.replace(/<br\s*\/?>/g, "; "); bot.pending = null; bot.mode = `Claude · ${log.length} tool call(s)`; bot.unverified = unverified(bot.content, log, q);
      return;
    }
    const tools = TOOLS.map(t => ({ name: t.name, description: t.description, inputSchema: t.inputSchema,
      execute: input => { bot.pending = `Querying Sakila: ${t.name}…`; paintChat(); const r = callTool(t.name, input, log); if (r && r.error) throw new Error(r.error); return JSON.stringify(r).length > 30000 ? JSON.stringify(r).slice(0, 30000) : r; } }));
    const { text } = await sampleFn([{ role: "user", content: RULES(q) }, ...turns], { tools, signal: busyCtl.signal,
      onText: ({ text }) => { bot.pending = null; bot.content = text; paintChat(); } });
    bot.content = text.replace(/<br\s*\/?>/g, "; "); bot.pending = null; bot.mode = `Claude · ${log.length} tool call(s)`; bot.unverified = unverified(bot.content, log, q);
  } catch (e) {
    bot.pending = null;
    if (e && ["not_granted", "sampling_disabled", "not_declared", "capability_disabled", "capability_removed", "tools_unavailable"].includes(e.code)) {
      sampleFn = null; paintStatus(); log.length = 0; bot.content = offline(q, log); bot.mode = "offline mode (Claude access not allowed) · answer built from tool results";
    } else if (e && e.code === "cancelled") { bot.content = (e.text || "") + "\n\n_Stopped._"; }
    else if (e && e.code === "rate_limited") { bot.content = (e.text || "") + "\n\n_Too many requests right now. Wait a moment, then ask again._"; }
    else { log.length = 0; bot.content = offline(q, log); bot.mode = `Claude call failed (${(e && e.code) || "error"}): answered in offline mode`; }
  } finally { busyCtl = null; const st = $("#stop"), sd = $("#send"); if (st) st.hidden = true; if (sd) sd.disabled = false; paintChat(); }
}

/* ------------------------------------------------------------------ router */
const ORDER = ["overview", "exploration", "transitions", "recommend", "agent"];
let current = null;
function route() {
  const h = (location.hash || "").replace("#", ""); const page = ORDER.includes(h) ? h : "overview";
  current = page;
  document.querySelectorAll("nav.tabs a").forEach(a => a.setAttribute("aria-current", a.dataset.tab === page ? "page" : "false"));
  $("#app").innerHTML = `<section class="page">${PAGES[page]()}</section>`;
  redraw(); window.scrollTo(0, 0);
}
function redraw() { draws.filter(d => d[0] === current).forEach(d => d[1]()); }
window.addEventListener("hashchange", route);
let rt; window.addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(redraw, 150); });
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", redraw);
new MutationObserver(redraw).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

document.addEventListener("click", e => {
  const b = e.target.closest("button"); if (!b) return;
  const sg = b.closest(".seg");
  if (sg) { sg.querySelectorAll("button").forEach(x => x.setAttribute("aria-pressed", x === b)); if (sg.id === "heatmode") { state.heat = b.dataset.v; drawHeat(); } if (sg.id === "rankby") { state.rankBy = b.dataset.v; drawTop(); } save(); return; }
  if (b.dataset.q) { ask(b.dataset.q); return; }
  if (b.id === "stop" && busyCtl) busyCtl.abort();
  if (b.id === "clear" && !busyCtl) { chat.length = 0; paintChat(); }
});
document.addEventListener("change", e => {
  const t = e.target;
  if (t.id === "jc") { state.journeyCustomer = +t.value; renderJourney(); }
  if (t.id === "fromcat") { state.fromCat = t.value; drawFrom(); }
  if (t.id === "rc") { state.customer = +t.value; renderReco(); }
  if (t.id === "rx") { state.exploration = t.checked; renderReco(); }
  if (t.id === "rs") { state.inStock = t.checked; renderReco(); }
  save();
});
document.addEventListener("submit", e => { if (e.target.id === "composer") { e.preventDefault(); const q = $("#qbox"); ask(q.value); q.value = ""; } });
document.addEventListener("keydown", e => { if (e.target.id === "qbox" && e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(e.target.value); e.target.value = ""; } });

$("#foot").innerHTML = `Data: official Sakila sample database (MySQL dump v1.5) · analysis window ${H.first_rental.slice(0, 10)} → ${H.last_rental.slice(0, 10)} (rentals before ${D.settings.end}; the anomalous 2006-02-14 batch is excluded). Statistics computed in Python (pandas, SciPy). Recommendations are recalculated live in this page with the same formula, verified against Python for all 599 customers.`;
if (!lastReco) { try { lastReco = { customer_id: state.customer, category: E.recommend(state.customer).recommended_category }; } catch (e) {} }
route();
initSample();
})();
