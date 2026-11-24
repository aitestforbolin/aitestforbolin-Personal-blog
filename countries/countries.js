(() => {
  const frame = document.querySelector(".country-map-frame");
  const tooltip = document.querySelector("[data-map-tooltip]");
  const tooltipFlag = document.querySelector("[data-map-tooltip-flag]");
  const tooltipName = document.querySelector("[data-map-tooltip-name]");
  const status = document.querySelector("[data-map-status]");

  if (!frame || !tooltip || !tooltipFlag || !tooltipName || !status) return;

  const countries = {
    italy: { flag: "🇮🇹", name: "意大利" },
    japan: { flag: "🇯🇵", name: "日本" },
    germany: { flag: "🇩🇪", name: "德国" },
    turkey: { flag: "🇹🇷", name: "土耳其" },
    spain: { flag: "🇪🇸", name: "西班牙" },
    "united-states": { flag: "🇺🇸", name: "美国" },
    "south-korea": { flag: "🇰🇷", name: "韩国" },
    bahrain: { flag: "🇧🇭", name: "巴林" },
    "united-kingdom": { flag: "🇬🇧", name: "英国" },
    netherlands: { flag: "🇳🇱", name: "荷兰" },
    denmark: { flag: "🇩🇰", name: "丹麦" },
    hungary: { flag: "🇭🇺", name: "匈牙利" },
    france: { flag: "🇫🇷", name: "法国" },
    thailand: { flag: "🇹🇭", name: "泰国" },
    vietnam: { flag: "🇻🇳", name: "越南" },
    malaysia: { flag: "🇲🇾", name: "马来西亚" },
    greece: { flag: "🇬🇷", name: "希腊" },
    switzerland: { flag: "🇨🇭", name: "瑞士" },
    sweden: { flag: "🇸🇪", name: "瑞典" },
    australia: { flag: "🇦🇺", name: "澳大利亚" },
    canada: { flag: "🇨🇦", name: "加拿大" },
    portugal: { flag: "🇵🇹", name: "葡萄牙" }
  };

  const defaultStatus = status.textContent.trim();
  const links = Array.from(frame.querySelectorAll(".map-country-link, .map-marker-link"));
  const groups = new Map();

  const slugFromLink = (link) => {
    const href = link.getAttribute("href") || "";
    return href.replace(/\/$/, "").split("/").pop();
  };

  links.forEach((link) => {
    const slug = slugFromLink(link);
    if (!groups.has(slug)) groups.set(slug, []);
    groups.get(slug).push(link);
  });

  const setRelatedState = (slug, active) => {
    (groups.get(slug) || []).forEach((link) => {
      link.classList.toggle("is-map-active", active);
    });
  };

  const positionTooltip = (clientX, clientY) => {
    const frameRect = frame.getBoundingClientRect();
    const tooltipRect = tooltip.getBoundingClientRect();
    const gap = 14;
    const edge = 10;

    let left = clientX - frameRect.left + gap;
    let top = clientY - frameRect.top + gap;

    if (left + tooltipRect.width > frameRect.width - edge) {
      left = clientX - frameRect.left - tooltipRect.width - gap;
    }
    if (top + tooltipRect.height > frameRect.height - edge) {
      top = clientY - frameRect.top - tooltipRect.height - gap;
    }

    tooltip.style.left = Math.max(edge, left) + "px";
    tooltip.style.top = Math.max(edge, top) + "px";
  };

  const showCountry = (link, clientX, clientY) => {
    const slug = slugFromLink(link);
    const country = countries[slug];
    if (!country) return;

    tooltipFlag.textContent = country.flag;
    tooltipName.textContent = country.name;
    tooltip.hidden = false;
    tooltip.setAttribute("aria-hidden", "false");

    status.textContent = country.flag + " " + country.name + " · 点击查看个人记录";
    status.classList.add("is-map-active");
    setRelatedState(slug, true);

    positionTooltip(clientX, clientY);
  };

  const hideCountry = (link) => {
    const slug = slugFromLink(link);
    setRelatedState(slug, false);
    tooltip.hidden = true;
    tooltip.setAttribute("aria-hidden", "true");
    status.textContent = defaultStatus;
    status.classList.remove("is-map-active");
  };

  links.forEach((link) => {
    link.addEventListener("pointerenter", (event) => {
      showCountry(link, event.clientX, event.clientY);
    });

    link.addEventListener("pointermove", (event) => {
      if (!tooltip.hidden) positionTooltip(event.clientX, event.clientY);
    });

    link.addEventListener("pointerleave", () => {
      if (document.activeElement !== link) hideCountry(link);
    });

    link.addEventListener("focus", () => {
      const target = link.querySelector(".map-country, .map-marker-dot") || link;
      const rect = target.getBoundingClientRect();
      showCountry(link, rect.left + rect.width / 2, rect.top + rect.height / 2);
    });

    link.addEventListener("blur", () => hideCountry(link));
  });
})();
