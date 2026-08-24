(function (global) {
  "use strict";

  const RAW_DATA_URL =
    "https://raw.githubusercontent.com/aitestforbolin/aitestforbolin-Personal-blog/main/data/crypto-fundraising.json";
  const CACHE_KEY = "bolin.cryptoFundraising.payload.v1";
  const REQUIRED_PROJECTS = 5;

  function validatePayload(data) {
    if (!data || typeof data !== "object") {
      throw new Error("Invalid fundraising payload");
    }

    const projects = Array.isArray(data.projects) ? data.projects.slice(0, REQUIRED_PROJECTS) : [];
    if (
      projects.length !== REQUIRED_PROJECTS ||
      projects.some((project) => !project || !String(project.name || "").trim())
    ) {
      throw new Error("Fundraising payload does not contain five valid projects");
    }

    return { ...data, projects };
  }

  function withCacheBust(value) {
    const url = new URL(value, global.location.href);
    url.searchParams.set("_", Date.now().toString());
    return url.toString();
  }

  async function fetchPayload(url) {
    const response = await global.fetch(withCacheBust(url), { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`Fundraising request failed: ${response.status}`);
    }
    return validatePayload(await response.json());
  }

  function saveCachedPayload(payload) {
    try {
      global.localStorage?.setItem(CACHE_KEY, JSON.stringify(payload));
    } catch (_error) {
      // Storage may be blocked in privacy modes. Network loading still works.
    }
  }

  function loadCachedPayload() {
    try {
      const raw = global.localStorage?.getItem(CACHE_KEY);
      if (!raw) return null;
      return validatePayload(JSON.parse(raw));
    } catch (_error) {
      return null;
    }
  }

  async function load(primaryUrl) {
    const attempts = [
      { url: primaryUrl, mode: "site" },
      { url: RAW_DATA_URL, mode: "github" },
    ];
    const errors = [];

    for (const attempt of attempts) {
      try {
        const payload = await fetchPayload(attempt.url);
        saveCachedPayload(payload);
        return { payload, mode: attempt.mode };
      } catch (error) {
        errors.push(error);
      }
    }

    const cached = loadCachedPayload();
    if (cached) {
      return { payload: cached, mode: "cache" };
    }

    const detail = errors.map((error) => error?.message || String(error)).join("; ");
    throw new Error(`Unable to load fundraising data: ${detail}`);
  }

  global.BolinFundraisingData = { load };
})(globalThis);
