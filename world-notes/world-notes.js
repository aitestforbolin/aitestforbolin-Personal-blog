(() => {
  const script = document.currentScript;
  const base = new URL('../', script.src);
  const root = document.querySelector('[data-world-notes]');
  if (!root) return;
  const mode = root.dataset.worldNotes;
  const list = root.querySelector('[data-wn-items]');
  const dateLabel = root.querySelector('[data-wn-date]');
  const countLabel = root.querySelector('[data-wn-count]');
  const archiveSelect = root.querySelector('[data-wn-archive]');
  let current;
  let generation = 0;
  const node = (tag, text) => {
    const el = document.createElement(tag);
    if (text) el.textContent = text;
    return el;
  };
  function link(text, url) {
    const el = node('a', text);
    const target = new URL(url, base);
    if (!['https:', 'http:'].includes(target.protocol)) throw new Error('Invalid source URL');
    el.href = target.href;
    el.target = '_blank';
    el.rel = 'noopener noreferrer';
    return el;
  }
  async function read(path) {
    const response = await fetch(new URL(path, base), {cache: 'no-store'});
    if (!response.ok) throw new Error('读取失败');
    return response.json();
  }
  function photo(item, index, article) {
    if (!item.image) return null; // Earlier editions remain readable without photos.
    try {
      const data = item.image;
      const url = new URL(data.url);
      if (url.protocol !== 'https:') return null;
      const figure = node('figure');
      figure.className = 'wn-photo';
      const original = link('', data.sourceUrl);
      original.setAttribute('aria-label', `${data.alt}，查看图片原文`);
      const img = node('img');
      img.alt = data.alt;
      img.loading = index === 0 ? 'eager' : 'lazy';
      img.decoding = 'async';
      const caption = node('figcaption');
      caption.append(node('span', data.caption));
      caption.append(link(`图片：${data.credit} ↗`, data.sourceUrl));
      // Keep the source accessible if a publisher stops serving its image.
      img.addEventListener('error', () => {
        original.replaceChildren(node('span', '到原文查看图片 ↗'));
        original.classList.add('wn-photo-unavailable');
      }, {once: true});
      original.append(img);
      figure.append(original, caption);
      img.src = url.href;
      article.classList.add('wn-illustrated');
      return figure;
    } catch (error) {
      return null;
    }
  }
  function render() {
    const selected = current.items;
    list.replaceChildren();
    dateLabel.textContent = current.reportDate;
    if (countLabel) countLabel.textContent = `${current.items.length} 条切片`;
    const more = root.querySelector('[data-wn-link]');
    if (more) more.href = new URL(`world-notes/?date=${current.reportDate}`, base);
    const visible = mode === 'brief' ? selected.slice(0, 1) : selected;
    visible.forEach((item, index) => {
      if (mode === 'home' || mode === 'brief') {
        const row = node('li');
        const title = node('a', item.title);
        title.href = new URL(`world-notes/?date=${current.reportDate}#${encodeURIComponent(item.id)}`, base);
        row.append(title);
        list.append(row);
        return;
      }
      const article = node('article');
      article.id = item.id;
      const number = node('span', String(index + 1).padStart(2, '0'));
      number.className = 'wn-number';
      number.setAttribute('aria-hidden', 'true');
      article.append(number, node('h2', item.title));
      const image = photo(item, index, article);
      if (image) article.append(image);
      const body = node('div');
      body.className = 'wn-body';
      item.body.split(/\n\s*\n/).filter(part => part.trim()).forEach(part => body.append(node('p', part.trim())));
      article.append(body);
      const footer = node('footer');
      footer.append(node('span', `${item.location} · ${item.materialDate}`));
      const sources = node('span');
      sources.className = 'wn-sources';
      item.sources.forEach((source, i) => {
        if (i) sources.append(document.createTextNode(' · '));
        sources.append(link(`${source.publisher} 原文 ↗`, source.url));
      });
      footer.append(sources);
      article.append(footer);
      list.append(article);
    });
    if (!visible.length) list.append(node('p', '本期暂无这类条目。'));
  }
  async function load(date) {
    const request = ++generation;
    try {
      const data = await read(date ? `data/world-notes/archive/${date}.json` : 'data/world-notes.json');
      if (request !== generation) return;
      if (!Array.isArray(data.items)) throw new Error('内容格式异常');
      current = data;
      render();
      if (mode === 'page' && location.hash) {
        const target = document.getElementById(decodeURIComponent(location.hash.slice(1)));
        if (target && list.contains(target)) target.scrollIntoView({behavior: 'instant', block: 'start'});
      }
    } catch (error) {
      if (request === generation) dateLabel.textContent = '暂时无法读取，请刷新重试。';
    }
  }
  const requested = new URLSearchParams(location.search).get('date');
  const date = /^\d{4}-\d{2}-\d{2}$/.test(requested || '') ? requested : null;
  load(date);
  if (archiveSelect) {
    read('data/world-notes/index.json').then(index => {
      archiveSelect.replaceChildren(new Option('最新一期', ''));
      index.dates.forEach(date => archiveSelect.add(new Option(date, date)));
      archiveSelect.value = date || '';
    }).catch(() => {});
    archiveSelect.addEventListener('change', () => {
      const date = archiveSelect.value;
      history.replaceState(null, '', date ? `?date=${date}` : location.pathname);
      load(date || null);
    });
  }
})();
