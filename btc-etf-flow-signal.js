(function () {
  const DATA_URL = "data/btc-etf-flow.json";

  const root = document.querySelector("[data-btc-etf-flow]");
  const summary = document.querySelector("[data-btc-etf-summary]");
  const trend = document.querySelector("[data-btc-etf-trend]");
  const updated = document.querySelector("[data-btc-etf-updated]");

  if (!root || !summary || !trend || !updated) {
    return;
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;");
  }

  function formatDate(value) {
    const date = new Date(`${value}T00:00:00Z`);
    if (Number.isNaN(date.getTime())) {
      return value || "-";
    }
    return new Intl.DateTimeFormat("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      timeZone: "UTC",
    })
      .format(date)
      .replace(/\//g, "-");
  }

  function formatUpdated(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return "更新中";
    }
    return new Intl.DateTimeFormat("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
      timeZone: "Asia/Shanghai",
    }).format(date);
  }

  function formatFlow(value) {
    if (!Number.isFinite(value)) {
      return "-";
    }
    const sign = value > 0 ? "+" : value < 0 ? "-" : "";
    return `${sign}${(Math.abs(value) / 100).toFixed(2)}亿美元`;
  }

  function valueClass(value) {
    if (!Number.isFinite(value) || value === 0) {
      return "flat";
    }
    return value > 0 ? "up" : "down";
  }

  function streak(rows) {
    const first = Number(rows[0]?.total);
    if (!Number.isFinite(first) || first === 0) {
      return "最新一日资金流持平";
    }
    const direction = first > 0 ? 1 : -1;
    let count = 0;
    for (const row of rows) {
      const value = Number(row.total);
      if (!Number.isFinite(value) || value * direction <= 0) {
        break;
      }
      count += 1;
    }
    return `连续 ${count} 个交易日${direction > 0 ? "净流入" : "净流出"}`;
  }

  function render(data) {
    const rows = Array.isArray(data.rows) ? data.rows : [];
    const latest = data.latest || rows[0] || {};
    const fiveDayTotal = rows.slice(0, 5).reduce((total, row) => {
      const value = Number(row.total);
      return total + (Number.isFinite(value) ? value : 0);
    }, 0);
    const cards = [
      ["最新一日", Number(latest.total), formatDate(latest.date)],
      ["近 5 个交易日", fiveDayTotal, "累计净流"],
    ];

    updated.textContent = `最新统计日：${formatDate(latest.date)} · 更新：${formatUpdated(data.updated_at)}`;
    summary.innerHTML = cards
      .map(([label, value, note]) => `
        <article class="btc-etf-signal-stat ${valueClass(value)}">
          <span>${escapeHtml(label)}</span>
          <strong>${formatFlow(value)}</strong>
          <small>${escapeHtml(note)}</small>
        </article>
      `)
      .join("");
    trend.textContent = streak(rows);
    root.classList.remove("is-error");
  }

  function renderError() {
    root.classList.add("is-error");
    updated.textContent = "数据暂时无法载入";
    summary.innerHTML = "";
    trend.textContent = "请查看 Farside 原始数据";
  }

  fetch(DATA_URL, { cache: "no-store" })
    .then((response) => {
      if (!response.ok) {
        throw new Error(`BTC ETF flow request failed: ${response.status}`);
      }
      return response.json();
    })
    .then((data) => {
      if (!Array.isArray(data.rows) || !data.rows.length) {
        throw new Error("BTC ETF flow has no rows");
      }
      render(data);
    })
    .catch(renderError);
})();
