(() => {
  const root = document.querySelector('[data-europe-watch-page]');
  if (!root) return;
  const updated = root.querySelector('[data-europe-watch-updated]');
  const note = root.querySelector('[data-europe-watch-note]');
  const filters = root.querySelector('[data-europe-watch-filters]');
  const regions = root.querySelector('[data-europe-watch-regions]');
  const list = root.querySelector('[data-europe-watch-list]');
  let allItems = [];
  let region = 'eu';
  let category = 'all';
  const regionLabels = { eu: '🇪🇺 欧盟', germany: '🇩🇪 德国' };
  const categoryLabels = {
    all: '全部', economy: '经济产业', work_income: '工作收入', housing: '住房生活',
    immigration: '移民', education: '教育', welfare_healthcare: '福利医疗',
    technology: '科技能源', energy: '科技能源', industry: '经济产业', trade: '经济产业',
    politics_society: '政治社会', defense_security: '政治社会', population: '政治社会'
  };

  const formatTime = value => {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? '' : date.toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  };

  const render = () => {
    const items = allItems.filter(item => item.region === region && (category === 'all' || categoryLabels[item.category] === categoryLabels[category]));
    list.replaceChildren();
    if (!items.length) {
      list.textContent = '暂时没有可显示的新闻。';
      return;
    }
    items.forEach(item => {
      const row = document.createElement('a');
      row.className = 'europe-watch-item';
      row.href = item.url;
      row.target = '_blank';
      row.rel = 'noreferrer';
      const meta = document.createElement('span');
      meta.className = 'europe-watch-item-meta';
      meta.textContent = `${item.source}｜${categoryLabels[item.category] || item.category}${formatTime(item.published_at) ? `｜${formatTime(item.published_at)}` : ''}`;
      const title = document.createElement('strong');
      title.textContent = item.title_cn || item.title;
      row.append(meta, title);
      list.append(row);
    });
  };

  const addRegion = code => {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = regionLabels[code];
    button.className = code === region ? 'is-active' : '';
    button.addEventListener('click', () => { region = code; [...regions.children].forEach(node => node.classList.toggle('is-active', node.textContent === regionLabels[code])); render(); });
    regions.append(button);
  };
  const addFilter = code => {
    const button = document.createElement('button'); button.type = 'button'; button.textContent = categoryLabels[code]; button.className = code === category ? 'is-active' : '';
    button.addEventListener('click', () => { category = code; [...filters.children].forEach(node => node.classList.toggle('is-active', node.textContent === categoryLabels[code])); render(); }); filters.append(button);
  };

  fetch('../data/europe-watch.json', { cache: 'no-store' })
    .then(response => { if (!response.ok) throw new Error('load failed'); return response.json(); })
    .then(data => {
      allItems = Array.isArray(data.items) ? data.items : [];
      updated.textContent = data.window_end
        ? `截至 ${formatTime(data.window_end)}，共 ${allItems.length} 条重点观察`
        : '最新 24 小时新闻';
      const sourceCount = Array.isArray(data.source_health) ? data.source_health.filter(item => item.status === 'ok').length : 0;
      note.textContent = sourceCount
        ? `过去 24 小时快照 · ${sourceCount} 个来源正常 · 仅保留筛选后的重点事项`
        : '过去 24 小时快照 · 仅保留筛选后的重点事项';
      ['eu', 'germany'].forEach(addRegion);
      ['all', 'economy', 'work_income', 'housing', 'immigration', 'education', 'welfare_healthcare', 'technology', 'politics_society'].forEach(addFilter);
      render();
    })
    .catch(() => { updated.textContent = '新闻数据暂时无法载入。'; note.textContent = ''; });
})();
