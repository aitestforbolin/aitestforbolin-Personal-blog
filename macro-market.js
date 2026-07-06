(function () {
  const DATA_URL = "data/macro-market.json";
  const REFRESH_INTERVAL = 60 * 1000;
  const FALLBACK_DATA = {
    updatedAt: "2026-07-06T12:05:00+08:00",
    items: [
      {
        id: "us-2y",
        label: "美国2年期国债",
        value: 4.17,
        unit: "%",
        date: "2026-07-01",
        sourceSeries: "DGS2",
      },
      {
        id: "us-10y",
        label: "美国10年期国债",
        value: 4.48,
        unit: "%",
        date: "2026-07-01",
        sourceSeries: "DGS10",
      },
      {
        id: "us-2y10y-spread",
        label: "2Y-10Y 利差",
        value: 0.31,
        unit: "pct pt",
        date: "2026-07-01",
        sourceSeries: "DGS10-DGS2",
      },
    ],
  };

  const root = document.querySelector("[data-macro-market]");
  const grid = document.querySelector("[data-macro-market-grid]");
  const updated = document.querySelector("[data-macro-market-updated]");

  if (!root || !grid || !updated) {
    return;
  }

  let refreshTimer = null;

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function formatValue(item) {
    const value = Number(item.value);
    if (!Number.isFinite(value)) {
      return "--";
    }

    if (item.unit === "%") {
      return `${value.toFixed(2)}%`;
    }

    if (item.unit === "pct pt") {
      return `${value >= 0 ? "+" : ""}${value.toFixed(2)} pct`;
    }

    return value.toLocaleString("en-US", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 4,
    });
  }

  function formatUpdatedLabel(value) {
    const timestamp = Date.parse(value);
    if (!Number.isFinite(timestamp)) {
      return "非实时数据";
    }

    const parts = new Intl.DateTimeFormat("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
      timeZone: "Asia/Shanghai",
    })
      .formatToParts(timestamp)
      .reduce((next, part) => {
        next[part.type] = part.value;
        return next;
      }, {});

    return `美债数据 ${parts.month}/${parts.day} ${parts.hour}:${parts.minute}`;
  }

  function renderEmpty(message) {
    grid.innerHTML = `<p class="macro-market-empty">${escapeHtml(message)}</p>`;
  }

  function render(data) {
    const items = Array.isArray(data.items) ? data.items : [];
    if (!items.length) {
      updated.textContent = "暂无美债数据";
      renderEmpty("美债数据暂时为空。");
      return;
    }

    updated.textContent = formatUpdatedLabel(data.updatedAt);
    grid.innerHTML = items
      .map((item) => {
        const date = item.date ? `数据日 ${item.date}` : "非实时数据";
        const source = item.sourceSeries ? `FRED ${item.sourceSeries}` : "FRED";
        return `
          <article class="macro-market-item">
            <span>${escapeHtml(item.label)}</span>
            <strong>${escapeHtml(formatValue(item))}</strong>
            <small>${escapeHtml(date)}</small>
            <em>${escapeHtml(source)}</em>
          </article>
        `;
      })
      .join("");
  }

  async function load() {
    try {
      const response = await fetch(`${DATA_URL}?v=${Date.now()}`, {
        cache: "no-store",
      });

      if (!response.ok) {
        throw new Error(`Macro market data unavailable: ${response.status}`);
      }

      render(await response.json());
    } catch (error) {
      render(FALLBACK_DATA);
      updated.textContent = `${updated.textContent} · 本地备份`;
    }
  }

  renderEmpty("正在载入美债数据...");
  load();
  refreshTimer = window.setInterval(load, REFRESH_INTERVAL);
  window.addEventListener("beforeunload", () => {
    window.clearInterval(refreshTimer);
  });
})();
