(function () {
  "use strict";

  // Keep the complete market/sector runtime and data pipeline intact, while the
  // homepage selector exposes only the three core cross-asset groups.
  const style = document.createElement("style");
  style.textContent = `
    [data-market-tabs] .market-pulse-tab-group:nth-child(n + 4) {
      display: none !important;
    }
  `;
  document.head.appendChild(style);

  const description = document.querySelector(
    ".market-prices-head > div > p:not(.eyebrow)"
  );
  if (description) {
    description.textContent =
      "在同一张图上切换美股指数、美元与美债收益率、商品与比特币，快速观察跨资产市场结构。";
  }

  const runtime = document.createElement("script");
  runtime.src = "market-prices-runtime.js?v=20260819-core-tabs-1";
  runtime.async = false;
  document.head.appendChild(runtime);
})();
