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
      title.textContent = item.originalTitle;
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
      updated.textContent = data.windowEnd
        ? `截至 ${formatTime(data.windowEnd)}，共 ${allItems.length} 条`
        : '最新 24 小时新闻';
      const sourceCount = Array.isArray(data.sourceAudit) ? data.sourceAudit.length : 0;
      note.textContent = sourceCount
        ? `收录此前 24 小时内曾出现在 ${sourceCount} 家 RSS 的全部标题`
        : '收录此前 24 小时内曾出现在 RSS 的全部标题';
      const countries = [...new Set(allItems.map(item => item.country))];
      const orderedCountries = countries.includes('德国')
        ? ['德国', ...countries.filter(name => name !== '德国')]
        : countries;
      ['全部', ...orderedCountries].forEach(addFilter);
      render();
    })
    .catch(() => { updated.textContent = '新闻数据暂时无法载入。'; note.textContent = ''; });
})();
