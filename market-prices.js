(function () {
  "use strict";

  // The full market/sector data pipeline lives in market-prices-runtime.js.
  // This entrypoint only narrows the homepage selector to the three core
  // cross-asset groups; sector symbols continue to be fetched and retained.
  const style = document.createElement("style");
  style.textContent = `
    [data-market-tabs] .market-pulse-tab-group:nth-child(n + 4) {
      display: none !important;
    }
  `;
  document.head.appendChild(style);

  const runtime = document.createElement("script");
  runtime.src = "market-prices-runtime.js?v=20260819-core-tabs-1";
  runtime.async = false;
  document.head.appendChild(runtime);
})();
