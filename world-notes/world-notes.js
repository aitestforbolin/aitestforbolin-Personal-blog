(() => {
  const script = document.currentScript;
  const base = new URL('../', script.src);
  const root = document.querySelector('[data-world-notes]');
  if (!root) return;
  const mode = root.dataset.worldNotes;
  const list = root.querySelector('[data-wn-items]');
  const dateLabel = root.querySelector('[data-wn-date]');
  const archiveSelect = root.querySelector('[data-wn-archive]');
  const filter = root.querySelector('[data-wn-filter]');
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
  function render() {
    const selected = current.items.filter(item => !filter || !filter.value || item.category === filter.value);
    list.replaceChildren();
    dateLabel.textContent = `${current.edition || ''} · ${current.reportDate}`.replace(/^ · /, '');
    const more = root.querySelector('[data-wn-link]');
    if (more) more.href = new URL(`world-notes/?date=${current.reportDate}`, base);
    const visible = mode === 'home' ? selected.slice(0, 2) : mode === 'brief' ? selected.slice(0, 1) : selected;
    visible.forEach(item => {
      const article = node('article');
      article.append(node('h3', item.title));
      if (mode !== 'brief') {
        article.append(node('p', item.body));
        const footer = node('footer', `${item.location} ｜ ${item.materialDate} ｜ ${item.evidenceType} ｜ `);
        item.sources.forEach((source, i) => {
          if (i) footer.append(document.createTextNode(' · '));
          footer.append(link(source.publisher, source.url));
        });
        article.append(footer);
        const evidence = node('details');
        evidence.append(node('summary', '看依据'));
        item.sources.forEach(source => evidence.append(node('p', source.evidence)));
        article.append(evidence);
      }
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
    } catch (error) {
      if (request === generation) dateLabel.textContent = '暂时无法读取，请刷新重试。';
    }
  }
  const requested = new URLSearchParams(location.search).get('date');
  const date = /^\d{4}-\d{2}-\d{2}$/.test(requested || '') ? requested : null;
  load(date);
  if (filter) filter.addEventListener('change', () => { if (current) render(); });
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
