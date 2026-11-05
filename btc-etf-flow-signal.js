(function () {
  const DATA_URL = "data/btc-etf-flow.json";

  const root = document.querySelector("[data-btc-etf-flow]");
  const summary = document.querySelector("[data-btc-etf-summary]");
  const updated = document.querySelector("[data-btc-etf-updated]");

  if (!root || !summary || !updated) {
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

  function streakInfo(rows, publishedCount) {
    const first = Number(rows[0]?.total);
    if (!Number.isFinite(first) || first === 0) {
      return { text: "最新一日资金流持平", direction: "flat" };
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
    const days = Number.isInteger(publishedCount) && publishedCount > 0 ? publishedCount : count;
    return {
      text: `连续 ${days} 个交易日${direction > 0 ? "净流入" : "净流出"}`,
      direction: direction > 0 ? "up" : "down",
    };
  }

  function render(data) {
    const rows = Array.isArray(data.rows) ? data.rows : [];
    const latest = data.latest || rows[0] || {};
    const fiveDays = rows.slice(0, 5).map((row) => row.total);
    const fiveDayTotal = fiveDays.length === 5 && fiveDays.every((value) =>
      typeof value === "number" && Number.isFinite(value)
    ) ? fiveDays.reduce((total, value) => total + value, 0) : NaN;
    const currentTrend = streakInfo(rows, latest.streak_days);
    const cards = [
      { label: "最新一日", value: Number(latest.total), note: formatDate(latest.date) },
      { label: "近 5 个交易日", value: fiveDayTotal, note: "累计净流" },
      { label: "当前趋势", value: currentTrend.text, note: "", className: currentTrend.direction },
    ];

    updated.textContent = `最新统计日：${formatDate(latest.date)} · 更新：${formatUpdated(data.updated_at)}`;
    summary.innerHTML = cards
      .map(({ label, value, note, className }) => `
        <article class="btc-etf-signal-stat ${className || valueClass(value)}">
          <span>${escapeHtml(label)}</span>
          <strong>${typeof value === "string" ? escapeHtml(value) : formatFlow(value)}</strong>
          <small>${escapeHtml(note)}</small>
        </article>
      `)
      .join("");
    root.classList.remove("is-error");
  }

  function renderError() {
    root.classList.add("is-error");
    updated.textContent = "数据暂时无法载入";
    summary.innerHTML = "";
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
