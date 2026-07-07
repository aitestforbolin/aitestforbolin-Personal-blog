(function () {
  const DATA_URL = "data/btc-etf-flow.json";
  const DISPLAY_FUNDS = [
    "GBTC",
    "IBIT",
    "FBTC",
    "ARKB",
    "BITB",
    "BTCO",
    "HODL",
    "BRRR",
    "EZBC",
    "BTCW",
    "BTC",
    "MSBT",
  ];
  const TABLE_ROWS = 10;
  const CHART_ROWS = 30;

  const root = document.querySelector("[data-btc-etf-flow]");
  const summary = document.querySelector("[data-btc-etf-summary]");
  const table = document.querySelector("[data-btc-etf-table]");
  const chart = document.querySelector("[data-btc-etf-chart]");
  const updated = document.querySelector("[data-btc-etf-updated]");

  if (!root || !summary || !table || !chart || !updated) {
    return;
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function formatDate(value) {
    const date = new Date(`${value}T00:00:00Z`);
    if (Number.isNaN(date.getTime())) {
      return value;
    }
    return new Intl.DateTimeFormat("zh-CN", {
      year: "numeric",
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

  function formatAxis(value) {
    if (!Number.isFinite(value)) {
      return "-";
    }
    const sign = value > 0 ? "+" : value < 0 ? "-" : "";
    return `${sign}${Math.abs(value).toFixed(0)}`;
  }

  function valueClass(value) {
    if (!Number.isFinite(value) || value === 0) {
      return "flat";
    }
    return value > 0 ? "up" : "down";
  }

  function renderSummary(data) {
    const latest = data.latest || {};
    const cards = [
      ["最新净流", latest.total, latest.date],
      ["近 7 个交易日", latest.seven_day_total, "合计"],
      ["近 30 个交易日", latest.thirty_day_total, "合计"],
    ];

    summary.innerHTML = cards
      .map(([label, value, note]) => {
        const numeric = Number(value);
        return `
          <article class="btc-etf-stat ${valueClass(numeric)}">
            <span>${escapeHtml(label)}</span>
            <strong>${formatFlow(numeric)}</strong>
            <small>${escapeHtml(note || "")}</small>
          </article>
        `;
      })
      .join("");
  }

  function renderTable(rows) {
    const visibleRows = rows.slice(0, TABLE_ROWS);
    const header = ["时间(UTC)", "总计", ...DISPLAY_FUNDS]
      .map((name) => `<th>${escapeHtml(name)}</th>`)
      .join("");

    const body = visibleRows
      .map((row, index) => {
        const total = row.total === null || row.total === undefined ? NaN : Number(row.total);
        const values = DISPLAY_FUNDS.map((fund) => {
          const rawValue = row.funds?.[fund];
          const value = rawValue === null || rawValue === undefined ? NaN : Number(rawValue);
          return `<td class="${valueClass(value)}">${formatFlow(value)}</td>`;
        }).join("");
        return `
          <tr class="${index === 0 ? "is-latest" : ""}">
            <th scope="row">${formatDate(row.date)}</th>
            <td class="${valueClass(total)}">${formatFlow(total)}</td>
            ${values}
          </tr>
        `;
      })
      .join("");

    table.innerHTML = `
      <table>
        <thead><tr>${header}</tr></thead>
        <tbody>${body}</tbody>
      </table>
    `;
  }

  function linePath(points, width, height, padding, min, max) {
    if (points.length < 2 || max <= min) {
      return "";
    }
    const step = (width - padding.left - padding.right) / (points.length - 1);
    return points
      .map((point, index) => {
        const x = padding.left + index * step;
        const y =
          padding.top +
          (1 - (point - min) / (max - min)) *
            (height - padding.top - padding.bottom);
        return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
      })
      .join(" ");
  }

  function renderChart(rows) {
    const points = rows.slice(0, CHART_ROWS).reverse();
    const width = 920;
    const height = 360;
    const padding = { top: 24, right: 22, bottom: 44, left: 56 };
    const totals = points.map((row) => Number(row.total || 0));
    const maxAbs = Math.max(100, ...totals.map((value) => Math.abs(value)));
    const zeroY = padding.top + (height - padding.top - padding.bottom) / 2;
    const step = (width - padding.left - padding.right) / Math.max(points.length, 1);
    const barWidth = Math.max(2, Math.min(8, step * 0.56));
    const pricePoints = points
      .map((row) => Number(row.btc_price))
      .filter((value) => Number.isFinite(value));
    const hasPrice = pricePoints.length > 3;
    const minPrice = hasPrice ? Math.min(...pricePoints) : 0;
    const maxPrice = hasPrice ? Math.max(...pricePoints) : 0;
    const priceLine = hasPrice
      ? linePath(
          points.map((row) => Number(row.btc_price || minPrice)),
          width,
          height,
          padding,
          minPrice,
          maxPrice
        )
      : "";

    const bars = points
      .map((row, index) => {
        const value = Number(row.total || 0);
        const x = padding.left + index * step + (step - barWidth) / 2;
        const scaled = Math.abs(value) / maxAbs;
        const barHeight = scaled * ((height - padding.top - padding.bottom) / 2);
        const y = value >= 0 ? zeroY - barHeight : zeroY;
        return `<rect class="btc-etf-bar ${valueClass(value)}" x="${x.toFixed(
          2
        )}" y="${y.toFixed(2)}" width="${barWidth.toFixed(2)}" height="${Math.max(
          1,
          barHeight
        ).toFixed(2)}" />`;
      })
      .join("");

    const labels = [points[0], points[Math.floor(points.length / 2)], points[points.length - 1]]
      .filter(Boolean)
      .map((row, index, list) => {
        const x =
          index === 0
            ? padding.left
            : index === list.length - 1
            ? width - padding.right
            : width / 2;
        return `<span style="left:${(x / width) * 100}%">${formatDate(row.date)}</span>`;
      })
      .join("");

    chart.innerHTML = `
      <div class="btc-etf-legend">
        <span><i class="inflow"></i>流入</span>
        <span><i class="outflow"></i>流出</span>
        ${hasPrice ? '<span><i class="price"></i>BTC价格</span>' : ""}
      </div>
      <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="BTC ETF资金流柱状图">
        <line class="btc-etf-zero" x1="${padding.left}" y1="${zeroY}" x2="${
      width - padding.right
    }" y2="${zeroY}" />
        <text class="btc-etf-axis" x="10" y="${padding.top + 6}">${formatAxis(maxAbs)}</text>
        <text class="btc-etf-axis" x="10" y="${zeroY + 4}">0</text>
        <text class="btc-etf-axis" x="10" y="${height - padding.bottom + 4}">-${formatAxis(
      maxAbs
    ).replace("+", "")}</text>
        ${bars}
        ${priceLine ? `<path class="btc-etf-price-line" d="${priceLine}" />` : ""}
      </svg>
      <div class="btc-etf-chart-dates">${labels}</div>
    `;
  }

  function renderError() {
    root.classList.add("is-error");
    updated.textContent = "数据暂时无法载入";
    summary.innerHTML = "";
    table.innerHTML = '<p class="btc-etf-empty">BTC ETF 资金流数据暂时无法载入。</p>';
    chart.innerHTML = "";
  }

  fetch(DATA_URL, { cache: "no-store" })
    .then((response) => {
      if (!response.ok) {
        throw new Error(`BTC ETF flow request failed: ${response.status}`);
      }
      return response.json();
    })
    .then((data) => {
      const rows = Array.isArray(data.rows) ? data.rows : [];
      if (!rows.length) {
        renderError();
        return;
      }
      updated.textContent = `更新：${formatUpdated(data.updated_at)}`;
      renderSummary(data);
      renderTable(rows);
      renderChart(rows);
    })
    .catch(renderError);
})();
