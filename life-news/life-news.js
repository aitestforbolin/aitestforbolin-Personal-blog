(() => {
  const root = document.querySelector('[data-life-news-page]');
  if (!root) return;
  const updated = root.querySelector('[data-life-news-updated]');
  const note = root.querySelector('[data-life-news-note]');
  const filters = root.querySelector('[data-life-news-filters]');
  const list = root.querySelector('[data-life-news-list]');
  let allItems = [];
  let country = '全部';

  const formatTime = value => {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? '' : date.toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  };

  const render = () => {
    const items = country === '全部' ? allItems : allItems.filter(item => item.country === country);
    list.replaceChildren();
    if (!items.length) {
      list.textContent = '暂时没有可显示的新闻。';
      return;
    }
    items.forEach(item => {
      const row = document.createElement('a');
      row.className = 'life-news-item';
      row.href = item.url;
      row.target = '_blank';
      row.rel = 'noreferrer';
      const meta = document.createElement('span');
      meta.className = 'life-news-item-meta';
      meta.textContent = `${item.country}｜${item.outlet}${formatTime(item.publishedAt) ? `｜${formatTime(item.publishedAt)}` : ''}`;
      const title = document.createElement('strong');
      title.textContent = item.chineseTitle || item.originalTitle;
      row.append(meta, title);
      list.append(row);
    });
  };

  const addFilter = name => {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = name;
    button.className = name === country ? 'is-active' : '';
    button.addEventListener('click', () => { country = name; [...filters.children].forEach(node => node.classList.toggle('is-active', node.textContent === name)); render(); });
    filters.append(button);
  };

  fetch('../data/life-society-news.json', { cache: 'no-store' })
    .then(response => { if (!response.ok) throw new Error('load failed'); return response.json(); })
    .then(data => {
      allItems = Array.isArray(data.items) ? data.items : [];
      updated.textContent = data.generatedAt ? `更新于 ${formatTime(data.generatedAt)}（北京时间）` : '最新更新';
      if (data.translationStatus === 'enabled') note.textContent = '中文标题由自动翻译生成；点击查看原文。';
      ['全部', ...new Set(allItems.map(item => item.country))].forEach(addFilter);
      render();
    })
    .catch(() => { updated.textContent = '新闻数据暂时无法载入。'; note.textContent = ''; });
})();
