(function () {
  "use strict";

  const homeRoot = document.querySelector("[data-us-macro-home]");
  const pageRoot = document.querySelector("[data-us-macro-page]");
  if (!homeRoot && !pageRoot) return;

  const DATA_URL = pageRoot
    ? "../data/us-macro-dashboard.json?v=20260819-2"
    : "data/us-macro-dashboard.json?v=20260819-2";

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function displayValue(value) {
    return value === null || value === undefined || value === "" ? "—" : escapeHtml(value);
  }

  function formatDate(value) {
    const parts = String(value || "").split("-");
    if (parts.length !== 3) return value || "—";
    return `${Number(parts[0])}年${Number(parts[1])}月${Number(parts[2])}日`;
  }

  function summaryCard(item) {
    return `
      <article class="us-macro-state" data-tone="${escapeHtml(item.tone)}">
        <span class="us-macro-state-label">${escapeHtml(item.label)}</span>
        <strong>${escapeHtml(item.state)}</strong>
        <p>${escapeHtml(item.detail)}</p>
      </article>
    `;
  }

  function metricCard(card) {
    const rows = (card.rows || []).map((row) => `
      <div class="us-macro-row">
        <span class="us-macro-row-label">${escapeHtml(row.label)}</span>
        <span>${displayValue(row.actual)}</span>
        <span>${displayValue(row.consensus)}</span>
        <span>${displayValue(row.previous)}</span>
      </div>
    `).join("");

    const consensusSources = (card.consensusSources || []).map((source) => `
      <a href="${escapeHtml(source.url)}" target="_blank" rel="noreferrer">
        ${escapeHtml(source.name)} ↗
      </a>
    `).join("");

    return `
      <article class="us-macro-card">
        <header class="us-macro-card-head">
          <div>
            <h3>${escapeHtml(card.title)}</h3>
            <span class="us-macro-period">${escapeHtml(card.period)}</span>
          </div>
          <a class="us-macro-source" href="${escapeHtml(card.source.url)}" target="_blank" rel="noreferrer">
            ${escapeHtml(card.source.name)} ↗
          </a>
        </header>
        <div class="us-macro-table">
          <div class="us-macro-row is-head">
            <span>指标</span><span>实际</span><span>预期</span><span>前值</span>
          </div>
          ${rows}
        </div>
        ${consensusSources ? `
          <p class="us-macro-consensus-source">
            <span>预期来源</span>${consensusSources}
          </p>
        ` : ""}
        ${card.revision ? `<p class="us-macro-revision">${escapeHtml(card.revision)}</p>` : ""}
        ${card.note ? `<p class="us-macro-note">${escapeHtml(card.note)}</p>` : ""}
        <p class="us-macro-trend">${escapeHtml(card.trend)}</p>
      </article>
    `;
  }

  function renderPage(data) {
    pageRoot.querySelector("[data-us-macro-updated]").textContent = formatDate(data.asOf);
    pageRoot.querySelector("[data-us-macro-summary]").innerHTML =
      (data.summary || []).map(summaryCard).join("");
    pageRoot.querySelector("[data-us-macro-groups]").innerHTML =
      (data.groups || []).map((group) => `
        <section class="us-macro-group" id="group-${escapeHtml(group.id)}">
          <div class="us-macro-section-head">
            <span>${escapeHtml(group.number)}</span>
            <div>
              <p class="eyebrow">${escapeHtml(group.id)}</p>
              <h2>${escapeHtml(group.title)}</h2>
              <p>${escapeHtml(group.description)}</p>
            </div>
          </div>
          <div class="us-macro-card-grid">
            ${(group.cards || []).map(metricCard).join("")}
          </div>
        </section>
      `).join("");
    pageRoot.querySelector("[data-us-macro-quality]").textContent =
      (data.dataQuality?.warnings || []).join(" ");
  }

  function renderHome(data) {
    homeRoot.querySelector("[data-us-macro-summary]").innerHTML =
      (data.summary || []).map(summaryCard).join("");
    homeRoot.querySelector("[data-us-macro-updated]").textContent =
      `数据截至 ${formatDate(data.asOf)}`;
  }

  fetch(DATA_URL, { cache: "no-store" })
    .then((response) => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.json();
    })
    .then((data) => {
      if (!Array.isArray(data.summary) || !Array.isArray(data.groups)) {
        throw new Error("invalid macro dashboard payload");
      }
      if (pageRoot) renderPage(data);
      if (homeRoot) renderHome(data);
    })
    .catch(() => {
      const message = "<p>宏观看板暂时无法载入，请稍后刷新。</p>";
      if (pageRoot) pageRoot.querySelector("[data-us-macro-summary]").innerHTML = message;
      if (homeRoot) homeRoot.querySelector("[data-us-macro-summary]").innerHTML = message;
    });
})();
