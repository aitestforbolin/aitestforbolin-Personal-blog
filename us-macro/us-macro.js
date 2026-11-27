(function () {
  "use strict";

  const homeRoot = document.querySelector("[data-us-macro-home]");
  const pageRoot = document.querySelector("[data-us-macro-page]");
  if (!homeRoot && !pageRoot) return;

  const DATA_URL = pageRoot
    ? "../data/us-macro-dashboard.json?v=20260917-ff-1"
    : "data/us-macro-dashboard.json?v=20260917-ff-1";

  const HOME_GROUPS = [
    {
      id: "inflation",
      title: "通胀",
      metrics: [
        { id: "cpi", row: "MoM", label: "CPI", basis: "环比" },
        { id: "core-cpi", row: "MoM", label: "核心 CPI", basis: "环比" },
        { id: "ppi", row: "MoM", label: "PPI", basis: "环比" },
        { id: "core-ppi", row: "MoM", label: "核心 PPI", basis: "环比" },
        { id: "core-pce", row: "MoM", label: "核心 PCE", basis: "环比" },
      ],
    },
    {
      id: "activity",
      title: "经济增长",
      metrics: [
        { id: "retail-sales", row: "Retail Sales m/m", label: "零售销售", basis: "名义环比" },
        { id: "core-retail-sales", row: "Core Retail Sales m/m", label: "核心零售销售", basis: "环比" },
        { id: "real-gdp", row: "GDP q/q", label: "实际 GDP", basis: "年化环比" },
      ],
    },
    {
      id: "employment",
      title: "就业",
      metrics: [
        { id: "nfp", row: "Non-Farm Employment Change", label: "非农新增", unit: "people" },
        { id: "unemployment", row: "Unemployment Rate", label: "失业率" },
        { id: "earnings", row: "MoM", label: "平均时薪", basis: "环比" },
      ],
    },
  ];
  const peopleFormatter = new Intl.NumberFormat("zh-CN", {
    maximumFractionDigits: 4,
    signDisplay: "exceptZero",
  });

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

  function numericValue(value) {
    if (value === null || value === undefined || value === "") return null;
    const parsed = Number.parseFloat(
      String(value).replaceAll(",", "").replace(/[+%kK]/g, "").trim()
    );
    return Number.isFinite(parsed) ? parsed : null;
  }

  function actualMovementClass(actual, previous) {
    const actualNumber = numericValue(actual);
    const previousNumber = numericValue(previous);
    if (actualNumber === null || previousNumber === null) return "";
    if (actualNumber > previousNumber) return "is-up";
    if (actualNumber < previousNumber) return "is-down";
    return "is-flat";
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
        <span class="us-macro-actual ${actualMovementClass(row.actual, row.previous)}">${displayValue(row.actual)}</span>
        <span>${displayValue(row.forecast ?? row.consensus)}</span>
        <span>${displayValue(row.previous)}</span>
      </div>
    `).join("");

    return `
      <article class="us-macro-card">
        <header class="us-macro-card-head">
          <div>
            <h3>${escapeHtml(card.title)}</h3>
            <span class="us-macro-period">${displayValue(card.period)}</span>
          </div>
          <a class="us-macro-source" href="${escapeHtml(card.sourceUrl)}" target="_blank" rel="noreferrer">
            ${escapeHtml(card.source)} ↗
          </a>
        </header>
        <div class="us-macro-table">
          <div class="us-macro-row is-head">
            <span>指标</span><span>实际</span><span>预期</span><span>前值</span>
          </div>
          ${rows}
        </div>
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

  function homeMetricValue(actual, metric) {
    if (metric.unit === "people") {
      const thousands = String(actual ?? "").trim().match(/^([+-]?\d[\d,]*(?:\.\d+)?)k$/i);
      if (thousands) {
        const people = Number(thousands[1].replaceAll(",", "")) / 10;
        return `${peopleFormatter.format(people)} 万人`;
      }
    }
    if (metric.basis && /^(?:\d+\.?\d*|\.\d+)%$/.test(String(actual)) && numericValue(actual) > 0) {
      return `+${displayValue(actual)}`;
    }
    return displayValue(actual);
  }

  function homeMetricPeriod(card) {
    if (card?.period) return `<span class="us-macro-home-period">${escapeHtml(card.period)}</span>`;
    const release = /^(\d{4})-(\d{2})-(\d{2})$/.exec(card?.releaseDate ?? "");
    if (!release) return "";
    const [date, , month, day] = release;
    return `<time class="us-macro-home-period" datetime="${date}" title="${formatDate(date)}公布">${Number(month)}月${Number(day)}日公布</time>`;
  }

  function homeMetricRow(metric, card) {
    const actual = card?.rows?.find((row) => row.label === metric.row)?.actual;
    const basis = metric.basis ? `<small>${metric.basis}</small>` : "";
    return `
      <div class="us-macro-home-row">
        <dt><span>${metric.label}</span>${basis}</dt>
        <dd>
          <strong>${homeMetricValue(actual, metric)}</strong>
          ${actual != null && actual !== "" ? homeMetricPeriod(card) : ""}
        </dd>
      </div>
    `;
  }

  function renderHome(data) {
    const cards = new Map(data.groups.flatMap((group) => group.cards || []).map((card) => [card.id, card]));
    const states = new Map(data.summary.map((item) => [item.id, item]));
    homeRoot.querySelector("[data-us-macro-home-grid]").innerHTML = HOME_GROUPS.map((group) => {
      const state = states.get(group.id);
      const badge = state?.state && state.state !== "待更新"
        ? `<span class="us-macro-home-badge" data-tone="${escapeHtml(state.tone)}">${escapeHtml(state.state)}</span>`
        : "";
      return `
        <article class="us-macro-home-card">
          <header class="us-macro-home-card-head">
            <h3>${group.title}</h3>
            ${badge}
          </header>
          <dl>${group.metrics.map((metric) => homeMetricRow(metric, cards.get(metric.id))).join("")}</dl>
        </article>
      `;
    }).join("");
    if (data.asOf) {
      homeRoot.querySelector("[data-us-macro-updated]").textContent = `数据截至 ${formatDate(data.asOf)}`;
    }
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
      if (homeRoot) {
        homeRoot.querySelector("[data-us-macro-home-grid]").innerHTML =
          '<p class="us-macro-home-status" role="status">宏观数据暂时无法载入，请稍后刷新。</p>';
      }
    });
})();
