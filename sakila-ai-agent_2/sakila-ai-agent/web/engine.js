/* Sakila analytics + recommendation engine (JS port of src/recommendation.py and src/tools.py).
   Works in the browser (window.SakilaEngine) and in node (module.exports) for parity tests. */
(function (root) {
  function Engine(D) {
    const cats = D.categories, K = cats.length, C = D.counts;
    const rowT = C.map(r => r.reduce((a, b) => a + b, 0));
    const colT = cats.map((_, j) => C.reduce((a, r) => a + r[j], 0));
    const N = rowT.reduce((a, b) => a + b, 0);
    const P = C.map((r, i) => r.map(v => v / rowT[i]));
    const base = colT.map(v => v / N);
    const lift = P.map(r => r.map((p, j) => p / base[j]));
    const Z = C.map((r, i) => r.map((v, j) => {
      const e = rowT[i] * base[j], rp = rowT[i] / N;
      return (v - e) / Math.sqrt(e * (1 - rp) * (1 - base[j]));
    }));
    const idx = Object.fromEntries(cats.map((c, i) => [c.toLowerCase(), i]));
    const film = id => { const f = D.films[id]; return f && { film_id: +id, title: f[0], category: cats[f[1]], rating: f[2], rental_rate: f[3], length: f[4], rentals_in_window: f[5], copies: f[6], available_copies: f[7], description: f[8] }; };
    const G = D.genre || { synonyms: {}, themes: {}, kid_words: [] };
    const reEsc = s => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    function resolveGenre(text) {
      const t = String(text || "").trim().toLowerCase();
      for (const c of cats) if (c.toLowerCase() === t || c.toLowerCase().replace(/s$/, "") === t.replace(/s$/, ""))
        return { requested: text, exact: true, categories: [c], description_keyword: null, kid_safe: G.kid_words.includes(c.toLowerCase()) };
      for (const k of Object.keys(G.synonyms).sort((a, b) => b.length - a.length))
        if (new RegExp(`\\b${reEsc(k)}\\b`).test(t)) return { requested: text, exact: false, categories: G.synonyms[k], description_keyword: G.themes[k] || null, kid_safe: G.kid_words.includes(k) };
      return { requested: text, exact: false, categories: [], description_keyword: null, kid_safe: false };
    }
    const r4 = x => Math.round(x * 1e4) / 1e4;

    function catIndex(name) {
      if (name == null) return -1;
      const k = String(name).trim().toLowerCase();
      return k in idx ? idx[k] : -1;
    }
    function journey(cid) {
      const c = D.customers[cid];
      if (!c) return null;
      let prev = null;
      return c.r.map(([fid, date, amount], i) => {
        const f = film(fid);
        const step = prev == null ? "first rental" : (prev === f.category ? "repeat" : "switch");
        prev = f.category;
        return { rental_number: i + 1, rental_date: date, film_id: fid, title: f.title, category: f.category, rating: f.rating, amount, transition: step };
      });
    }
    function scoreCategories(history, wT, wA) {
      const last = catIndex(history[history.length - 1]);
      const counts = new Array(K).fill(0);
      history.forEach(h => counts[catIndex(h)]++);
      const tot = (wT + wA) || 1;
      return cats.map((c, j) => {
        const tp = P[last][j], aff = (counts[j] + 1) / (history.length + K);
        return { category: c, transition_probability: tp, affinity: aff, customer_rentals_in_category: counts[j],
          score: (wT * tp + wA * aff) / tot, lift: lift[last][j], z_residual: Z[last][j], transitions_from_last: C[last][j] };
      }).sort((a, b) => (b.score - a.score) || (b.transition_probability - a.transition_probability));
    }
    function recommendMovies(cid, category, n, availableOnly) {
      const c = D.customers[cid];
      const seen = new Set([...c.r.map(x => x[0]), ...c.x]);
      const ci = catIndex(category);
      return Object.keys(D.films).map(film)
        .filter(f => f.category === cats[ci] && !seen.has(f.film_id) && f.copies > 0 && (!availableOnly || f.available_copies > 0))
        .sort((a, b) => (b.rentals_in_window - a.rentals_in_window) || (b.available_copies - a.available_copies) || (a.title < b.title ? -1 : 1))
        .slice(0, n);
    }
    function recommend(cid, opts = {}) {
      const { exploration = false, nMovies = 5, nCategories = 3, availableOnly = true } = opts;
      const j = journey(cid);
      if (!j) throw new Error(`Customer ${cid} does not exist. Valid IDs are 1-599.`);
      const hist = j.map(x => x.category), last = hist[hist.length - 1], li = catIndex(last);
      let ranked = scoreCategories(hist, D.settings.w_t, D.settings.w_a);
      if (exploration) ranked = ranked.filter(r => r.category !== last);
      const top = ranked[0], it = D.independence;
      const strength = (it.p_value >= 0.05 || Math.abs(top.z_residual) < 1.96) ? "weak" : "moderate";
      const alt = {};
      ranked.slice(1, nCategories).forEach(r => { alt[r.category] = recommendMovies(cid, r.category, 3, availableOnly).map(m => m.title); });
      return {
        customer_id: +cid, customer_name: D.customers[cid].n, rentals_in_window: hist.length,
        recent_categories: hist.slice(-5), last_rental_date: j[j.length - 1].rental_date,
        current_category: last, mode: exploration ? "exploration (current category excluded)" : "standard",
        recommended_category: top.category, score: r4(top.score), transition_probability: r4(top.transition_probability),
        transitions_observed: top.transitions_from_last, outgoing_transitions_from_current: rowT[li],
        lift_vs_baseline: Math.round(top.lift * 1000) / 1000, z_residual: Math.round(top.z_residual * 100) / 100,
        customer_affinity: r4(top.affinity), customer_rentals_in_recommended_category: top.customer_rentals_in_category,
        signal_strength: strength, weights: { transition: D.settings.w_t, affinity: D.settings.w_a },
        ranked_categories: ranked.slice(0, Math.max(nCategories, 8)).map(r => ({ ...r, score: r4(r.score), transition_probability: r4(r.transition_probability), affinity: r4(r.affinity), lift: r4(r.lift), z_residual: Math.round(r.z_residual * 100) / 100 })),
        recommended_movies: recommendMovies(cid, top.category, nMovies, availableOnly),
        alternative_category_movies: alt,
        global_signal: { chi2_p_value: it.p_value, cramers_v: it.cramers_v },
      };
    }
    function categoryProfile(name, direction = "outgoing", topN = 5) {
      const i = catIndex(name);
      if (i < 0) throw new Error(`Unknown category '${name}'. Valid: ${cats.join(", ")}`);
      const it = D.independence;
      const stat = { p_value: it.p_value, cramers_v: it.cramers_v, uniform_probability: it.uniform_probability, cells_significant_after_bonferroni: it.cells_significant_after_bonferroni };
      if (direction === "incoming") {
        const src = cats.map((c, k) => ({ from_category: c, transitions: C[k][i], probability_from_source: r4(P[k][i]), lift: Math.round(lift[k][i] * 1000) / 1000, z_residual: Math.round(Z[k][i] * 100) / 100 }))
          .filter((_, k) => k !== i).sort((a, b) => b.probability_from_source - a.probability_from_source).slice(0, topN);
        return { category: cats[i], direction: "incoming", incoming_transitions: colT[i], top_source_categories: src, statistical_context: stat,
          meaning: "probability_from_source = P(next is this category | previous was source). Chance level = 6.25%." };
      }
      const dest = cats.map((c, k) => ({ to_category: c, transitions: C[i][k], probability: r4(P[i][k]), baseline_share: r4(base[k]), lift: Math.round(lift[i][k] * 1000) / 1000, z_residual: Math.round(Z[i][k] * 100) / 100 }))
        .filter((_, k) => k !== i).sort((a, b) => b.probability - a.probability);
      return { category: cats[i], direction: "outgoing", outgoing_transitions: rowT[i], incoming_transitions: colT[i],
        unique_destination_categories: dest.filter(d => d.transitions > 0).length, self_transition_probability: r4(P[i][i]),
        top_destinations: dest.slice(0, topN), statistical_context: stat,
        reading_guide: "Probabilities near 6.25% equal chance. |z|>1.96 is nominal; ~13 of 256 cells exceed it by chance." };
    }
    function topTransitions(n = 15, sortBy = "transitions") {
      const out = [];
      for (let i = 0; i < K; i++) for (let k = 0; k < K; k++) if (i !== k)
        out.push({ from_category: cats[i], to_category: cats[k], transitions: C[i][k], probability: P[i][k], lift: lift[i][k], z_residual: Z[i][k] });
      return out.sort((a, b) => (b[sortBy] - a[sortBy]) || (b.transitions - a.transitions)).slice(0, n);
    }
    function searchMovies({ category, title, rating, available_only = false, limit = 10, sort_by = "popularity", keyword } = {}) {
      let fs = Object.keys(D.films).map(film), note = null, theme = null;
      if (category) {
        const g = resolveGenre(category);
        if (!g.categories.length) throw new Error(`'${category}' is not a Sakila category and has no close match. Valid categories: ${cats.join(", ")}`);
        fs = fs.filter(f => g.categories.includes(f.category));
        if (!g.exact) { note = `Sakila has no '${category}' category. Closest categories: ${g.categories.join(", ")}` + (g.description_keyword ? `; films whose description mentions '${g.description_keyword}' are listed first.` : "."); theme = g.description_keyword; }
        if (g.kid_safe && !rating) { fs = fs.filter(f => f.rating === "G" || f.rating === "PG"); note = (note ? note + " " : "") + "Only G and PG rated films are shown for a family/kids request."; }
      }
      if (title) fs = fs.filter(f => f.title.toLowerCase().includes(String(title).toLowerCase()));
      if (keyword) { const k = String(keyword).toLowerCase(); fs = fs.filter(f => f.title.toLowerCase().includes(k) || f.description.toLowerCase().includes(k)); }
      if (rating) fs = fs.filter(f => f.rating.toUpperCase() === String(rating).toUpperCase());
      if (available_only) fs = fs.filter(f => f.available_copies > 0);
      const key = { popularity: ["rentals_in_window", -1], title: ["title", 1], rental_rate: ["rental_rate", -1], length: ["length", -1] }[sort_by] || ["rentals_in_window", -1];
      const th = f => theme && f.description.toLowerCase().includes(theme.toLowerCase()) ? 1 : 0;
      fs.sort((a, b) => (th(b) - th(a)) || (a[key[0]] < b[key[0]] ? -1 : a[key[0]] > b[key[0]] ? 1 : 0) * key[1]);
      const out = { matches: fs.length, movies: fs.slice(0, Math.min(+limit || 10, 25)), availability_definition: "available_copies = copies not out on an unreturned rental (dataset snapshot).",
        business_model: "Sakila RENTS DVDs (rental_rate per rental); it does not sell them." };
      if (note) out.genre_note = note;
      return out;
    }
    function customerHistory(cid, maxRentals = 30) {
      const c = D.customers[cid], j = journey(cid);
      if (!c) throw new Error(`Customer ${cid} does not exist. Valid IDs are 1-599.`);
      const counts = {}; j.forEach(x => counts[x.category] = (counts[x.category] || 0) + 1);
      return { customer: { customer_id: +cid, name: c.n, location: c.loc }, rental_count: j.length, distinct_categories: Object.keys(counts).length,
        category_counts: counts, repeat_transitions: j.filter(x => x.transition === "repeat").length, switch_transitions: j.filter(x => x.transition === "switch").length,
        category_journey: j.map(x => x.category).join(" -> "), rentals: j.slice(-maxRentals),
        note: `Showing the last ${Math.min(maxRentals, j.length)} of ${j.length} rentals in the analysis window.` };
    }
    const METRICS = {
      overview: () => D.headline,
      stores: () => ({ total_stores: D.stores.length, stores: D.stores, note: "Rentals/revenue attributed to the store owning the rented copy (inventory.store_id)." }),
      total_customers: () => ({ total_customers: D.headline.total_customers, renting_customers: D.headline.renting_customers }),
      total_rentals: () => ({ total_rentals: D.headline.total_rentals }),
      total_revenue: () => ({ total_revenue: D.headline.total_revenue }),
      average_rental_rate: () => ({ avg_catalog_rental_rate: D.headline.avg_catalog_rental_rate, avg_payment_per_rental: D.headline.avg_payment_per_rental }),
      most_rented_categories: () => D.category_perf.map(r => ({ category: r.category, rentals: r.rentals, rental_share_pct: r.rental_share_pct, customers: r.customers })),
      category_revenue: () => D.category_perf.map(r => ({ category: r.category, revenue: r.revenue, revenue_share_pct: r.revenue_share_pct, avg_rental_rate: r.avg_rental_rate })),
      rental_trends: () => D.monthly,
      customer_return: () => D.return,
      repeat_vs_switch: () => ({ ...D.repetition, field_meanings: { shuffled_repeat_p_value: "PERMUTATION test p-value (observed repeat rate vs each customer's shuffled history). NOT the chi-square test.", random_choice_repeat_pct: "repeat rate expected if categories were picked at random (sum of p^2)" } }),
      revenue_breakdown: () => D.revenue_breakdown,
      inventory_utilization: () => D.inventory_utilization,
      key_insights: () => ({ count: D.team_insights.length, insights: D.team_insights.map(x => ({ id: x.id, title: x.title, business_question: x.business_question, verified_findings: x.verified_findings })) }),
      verified_facts: () => D.key_insights,
      chronology: () => D.chronology,
      customer_segments: () => D.segments,
      category_share_by_burst: () => D.cat_burst,
      misc_facts: () => D.misc,
      category_diversity: () => D.diversity,
      transition_statistics: () => ({ ...D.independence, field_meanings: { p_value: "CHI-SQUARE independence test p-value (previous vs next category)", cramers_v: "association strength; below 0.1 = negligible" } }),
      top_transitions: () => topTransitions(10).map(t => ({ ...t, probability: r4(t.probability), lift: r4(t.lift), z_residual: Math.round(t.z_residual * 100) / 100 })),
      high_transition_categories: () => ({ assessment: D.gateway, table: D.high_transition }),
      recommendation_backtest: () => D.backtest,
    };
    function metric(name) {
      const k = String(name || "").trim().toLowerCase().replace(/ /g, "_");
      if (!METRICS[k]) throw new Error(`Unknown metric '${name}'. Available: ${Object.keys(METRICS).join(", ")}`);
      return { metric: k, analysis_window_end: D.headline.analysis_end_date, value: METRICS[k]() };
    }
    function getInsights(id) {
      if (id == null || id === "" || id === 0 || id === "all") return METRICS.key_insights();
      const x = D.team_insights.find(t => t.id === +id);
      if (!x) throw new Error("insight_id must be 1-6");
      return x;
    }
    function dataLimitations(topic) {
      const t = String(topic || "").toLowerCase();
      const hit = D.limits.filter(l => !t || l.topic.includes(t) || l.limitation.toLowerCase().includes(t));
      return { limitations: hit.length ? hit : D.limits };
    }
    const getTrends = g => D.trends[g] || D.trends.month;
    return { getInsights, dataLimitations, getTrends, D, cats, C, P, base, lift, Z, rowT, colT, N, catIndex, journey, scoreCategories, recommend, recommendMovies,
      categoryProfile, topTransitions, searchMovies, resolveGenre, customerHistory, metric, METRIC_NAMES: Object.keys(METRICS), film };
  }
  if (typeof module !== "undefined" && module.exports) module.exports = Engine; else root.SakilaEngine = Engine;
})(typeof window !== "undefined" ? window : globalThis);
