(function () {
  "use strict";

  const API_URL =
    "https://cross-asset-pulse.laibocszd.chatgpt.site/api/markets?range=1d";
  const REFRESH_INTERVAL = 60 * 1000;
  const FETCH_TIMEOUT = 10 * 1000;
  const CACHE_KEY = "bolin-home-market-snapshot-v1";

  const MARKETS = [
    { key: "SPX", ids: ["SPX"], name: "S&P 500", code: "SPX", decimals: 2, tradingView: "SP:SPX" },
    { key: "IXIC", ids: ["IXIC"], name: "Nasdaq Composite", code: "IXIC", decimals: 2, tradingView: "NASDAQ:IXIC" },
    { key: "US02Y", ids: ["US02Y"], name: "美国 2Y", code: "财政部日度", decimals: 2, unit: "yield", tradingView: "TVC:US02Y" },
    { key: "US10Y", ids: ["US10Y"], name: "美国 10Y", code: "财政部日度", decimals: 2, unit: "yield", tradingView: "TVC:US10Y" },
    { key: "DXY", ids: ["DXY"], name: "美元指数", code: "DXY", decimals: 2, tradingView: "TVC:DXY" },
    { key: "GOLD", ids: ["GC1!", "GC=F", "GOLD"], name: "Gold", code: "COMEX GC1!", fallbackCode: "XAU/USD 现货参考", decimals: 2, currency: true, tradingView: "COMEX:GC1!" },
    { key: "BRN1!", ids: ["BRN1!"], name: "Brent", code: "BRN1!", decimals: 2, currency: true, tradingView: "ICEEUR:BRN1!" },
    { key: "BTCUSDT", ids: ["BTCUSDT"], name: "Bitcoin", code: "BTC", decimals: 0, currency: true, tradingView: "BINANCE:BTCUSDT" },
  ];

  const root = document.querySelector("[data-market-snapshot]");
  const grid = document.querySelector("[data-market-snapshot-grid]");
  const status = document.querySelector("[data-market-snapshot-status]");
  if (!root || !grid || !status) return;

  function formatNumber(value, market) {
    if (!Number.isFinite(value)) return "—";
    const formatted = new Intl.NumberFormat("en-US", {
      minimumFractionDigits: market.decimals,
      maximumFractionDigits: market.decimals,
    }).format(value);
    if (market.unit === "yield") return `${formatted}%`;
    return market.currency ? `$${formatted}` : formatted;
  }

  function formatChange(quote, market) {
    if (market.unit === "yield") {
      const change = Number(quote.change);
      if (!Number.isFinite(change)) return { text: "—", direction: "flat" };
      const basisPoints = change * 100;
      return {
        text: `${basisPoints > 0 ? "+" : ""}${basisPoints.toFixed(1)} bp`,
        direction: basisPoints > 0 ? "up" : basisPoints < 0 ? "down" : "flat",
      };
    }
    const changePercent = Number(quote.changePercent);
    if (!Number.isFinite(changePercent)) return { text: "—", direction: "flat" };
    return {
      text: `${changePercent > 0 ? "+" : ""}${changePercent.toFixed(2)}%`,
      direction: changePercent > 0 ? "up" : changePercent < 0 ? "down" : "flat",
    };
  }

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function render(data, cached) {
    const quotes = new Map(data.map((item) => [item.id, item]));
    let goldUsesSpotFallback = false;
    grid.innerHTML = MARKETS.map((market) => {
      const matchedId = market.ids.find((id) => quotes.has(id));
      const quote = matchedId ? quotes.get(matchedId) : null;
      const isGoldSpotFallback = market.key === "GOLD" && matchedId === "GOLD";
      goldUsesSpotFallback ||= isGoldSpotFallback;
      const detail = isGoldSpotFallback ? market.fallbackCode : market.code;
      const change = quote ? formatChange(quote, market) : { text: "暂不可用", direction: "flat" };
      const href = `https://www.tradingview.com/chart/?symbol=${encodeURIComponent(market.tradingView)}`;
      return `
        <a class="market-quote-card" href="${href}" target="_blank" rel="noreferrer"
          aria-label="在 TradingView 打开 ${escapeHtml(market.name)}">
          <span class="market-quote-primary">
            <span class="market-quote-heading"><strong>${escapeHtml(market.name)}</strong><small>${escapeHtml(detail)}</small></span>
            <span class="market-quote-value">${formatNumber(quote ? Number(quote.price) : NaN, market)}</span>
          </span>
          <span class="market-quote-change is-${change.direction}">${escapeHtml(change.text)}</span>
        </a>`;
    }).join("");

    const timestamps = data.map((quote) => Number(quote.updatedAt)).filter(Number.isFinite);
    const latest = timestamps.length ? Math.max(...timestamps) : Date.now();
    const time = new Intl.DateTimeFormat("zh-CN", {
      timeZone: "Asia/Shanghai",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(new Date(latest));
    const notes = [cached ? `缓存数据 · ${time}` : `更新于 ${time}`];
    if (goldUsesSpotFallback) notes.push("Gold 暂用现货参考");
    status.textContent = notes.join(" · ");
    root.setAttribute("aria-busy", "false");
  }

  function readCache() {
    try {
      const cached = JSON.parse(localStorage.getItem(CACHE_KEY));
      return Array.isArray(cached) ? cached : null;
    } catch (_error) {
      return null;
    }
  }

  function writeCache(data) {
    try {
      localStorage.setItem(CACHE_KEY, JSON.stringify(data));
    } catch (_error) {
      // The live quote should still render when browser storage is unavailable.
    }
  }

  async function refresh() {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), FETCH_TIMEOUT);
    try {
      const response = await fetch(API_URL, { cache: "no-store", signal: controller.signal });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      if (!Array.isArray(payload.data)) throw new Error("Invalid market payload");
      writeCache(payload.data);
      render(payload.data, false);
    } catch (_error) {
      const cached = readCache();
      if (cached) render(cached, true);
      else {
        render([], true);
        status.textContent = "行情暂时不可用，可通过 TradingView 查看";
      }
    } finally {
      window.clearTimeout(timeout);
    }
  }

  const cached = readCache();
  if (cached) render(cached, true);
  refresh();
  window.setInterval(refresh, REFRESH_INTERVAL);
})();
