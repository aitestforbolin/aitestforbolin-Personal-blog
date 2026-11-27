(() => {
  const target = document.querySelector("[data-new-findings]");
  const script = document.currentScript;
  if (!target || !script) return;

  const items = target.querySelector("[data-nf-items]");
  const status = target.querySelector("[data-nf-status]");
  const dataUrl = new URL("../data/new-findings.json", script.src);
  const reader = new URL("./", script.src);

  function make(tag, value = "", style = "") {
    const result = document.createElement(tag);
    if (value) result.textContent = value;
    if (style) result.className = style;
    return result;
  }

  function link(text, href, style) {
    const result = make("a", text, style);
    result.href = href;
    return result;
  }

  function dateUrl(id, item) {
    const url = new URL(reader);
    url.searchParams.set("edition", id);
    if (item) url.hash = "finding-" + item;
    return url.href;
  }

  function safeSource(value) {
    try {
      const url = new URL(value);
      return ["https:", "http:"].includes(url.protocol) ? url.href : null;
    } catch {
      return null;
    }
  }

  function renderHome(edition) {
    const frame = make("div", "", "nf-grid");
    const [featured, ...shorts] = edition.items;
    if (!shorts.length) frame.classList.add("nf-grid--single");
    function card(item, style) {
      const article = make("article", "", style);
      const heading = make("h3");
      heading.append(link(item.title, dateUrl(edition.id, item.id)));
      article.append(make("p", item.category, "nf-label"), heading, make("p", item.summary, "nf-summary"));
      return article;
    }
    frame.append(card(featured, "nf-lead"));
    if (shorts.length) {
      const rail = make("div");
      shorts.forEach(item => rail.append(card(item, "nf-short")));
      frame.append(rail);
    }
    items.append(frame);
    target.querySelector("[data-nf-meta]").textContent = edition.date + " · " + edition.items.length + " 条";
  }

  function renderReader(editions) {
    const archive = target.querySelector("[data-nf-archive]");
    const requested = new URLSearchParams(window.location.search).get("edition");
    const edition = requested ? editions.find(entry => entry.id === requested) : editions[0];
    editions.forEach(entry => {
      const archiveLink = link(entry.id, dateUrl(entry.id));
      if (entry === edition) archiveLink.setAttribute("aria-current", "page");
      archive.append(archiveLink);
    });
    if (!edition) {
      status.textContent = "找不到这一期，可以从往期列表选择其他期。";
      return false;
    }
    items.append(make("h2", edition.date + " · " + edition.items.length + " 条", "nf-edition-heading"));
    edition.items.forEach(item => {
      const article = make("article", "", "nf-article");
      article.id = "finding-" + item.id;
      article.append(make("p", [item.category, item.evidence].filter(Boolean).join(" · "), "nf-label"),
        make("h2", item.title), make("p", item.summary, "nf-summary"));
      if (item.update_of) {
        const prior = make("p");
        prior.append(make("span", item.what_changed + " "), link("阅读上次报道", dateUrl(item.update_of, item.id), "nf-link"));
        article.append(prior);
      }
      (item.details || []).forEach(detail => article.append(make("p", detail)));
      const sources = make("ul", "", "nf-source");
      item.sources.forEach(source => {
        const url = safeSource(source.url);
        if (!url) return;
        const row = make("li");
        row.append(link(source.title, url));
        sources.append(row);
      });
      if (sources.childElementCount) article.append(sources);
      items.append(article);
    });
    if (window.location.hash) document.getElementById(window.location.hash.slice(1))?.scrollIntoView();
    return true;
  }

  fetch(dataUrl, { cache: "no-cache" })
    .then(response => {
      if (!response.ok) throw new Error("Cannot load New Findings");
      return response.json();
    })
    .then(({ editions }) => {
      if (!editions.length) {
        status.textContent = "首期正在整理，发布后将在这里显示。";
        return;
      }
      if (target.dataset.newFindings === "home") {
        renderHome(editions[0]);
        status.hidden = true;
      } else if (renderReader(editions)) {
        status.hidden = true;
      }
    })
    .catch(() => {
      status.textContent = "本期暂时无法载入，请稍后刷新。";
    });
})();
