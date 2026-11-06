/* API data is rendered as text. CSV generation and all crawling live in Python. */
(() => {
  'use strict';
  const Data = window.HospitalData;
  const $ = id => document.getElementById(id);
  const ACTIVE = new Set(['queued', 'fetching_list', 'fetching_details', 'saving']);
  const LABELS = { queued:'等待执行', fetching_list:'读取列表', fetching_details:'采集详情', saving:'保存结果', completed:'采集完成', partial:'部分完成', failed:'任务失败', interrupted:'任务中断' };
  const state = { jobs:[], filtered:[], task:null, resultTask:null, page:1, size:10,
    connected:false, starting:false, downloading:false, syncing:null, notified:'', syncError:false };
  const number = value => value.toLocaleString('zh-CN');
  const percent = (value, total) => total ? Math.round(value / total * 100) : 0;
  const titleOf = job => job.title || '未获取岗位名称';
  const shortID = task => task.id.slice(0, 8);
  const dateText = value => value ? new Date(value).toLocaleString('zh-CN', { hour12:false }) : '—';
  const historical = () => state.resultTask && state.task && state.resultTask.id !== state.task.id;
  const testData = task => task?.source_kind === 'local_html_test';
  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function message(text, error=false) {
    $('feedback').textContent = text;
    $('feedback').className = error ? 'feedback error' : 'feedback';
    $('feedback').hidden = false;
  }
  async function api(path, options={}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 10000);
    try {
      const response = await fetch(path, { ...options, cache:'no-store', signal:controller.signal });
      const body = await response.json();
      if (!response.ok) {
        const error = new Error(typeof body.detail === 'string' ? body.detail : body.detail?.message || `服务返回 HTTP ${response.status}`);
        error.status = response.status; error.detail = body.detail; throw error;
      }
      return body;
    } finally { clearTimeout(timer); }
  }
  function filters() {
    return { title:$('title-search').value, major:$('major-search').value,
      education:$('education-filter').value, missing:$('missing-filter').value, sort:$('sort-select').value };
  }
  function renderOverview() {
    const stats = Data.summarize(state.jobs);
    ['total','education','major','complete'].forEach(key => { $(`stat-${key}`).textContent = number(stats[key]); });
    $('nav-count').textContent = number(stats.total);
    ['education','major'].forEach(key => { $(`stat-${key}-note`).textContent = stats.total ? `覆盖 ${percent(stats[key], stats.total)}% 的岗位` : '采集完成后计算覆盖率'; });
    $('quality-percent').textContent = stats.total ? `${percent(stats.complete, stats.total)}%` : '—';
    $('quality-bar').style.width = `${percent(stats.complete, stats.total)}%`;
    $('quality-description').textContent = stats.total ? `${number(stats.total - stats.complete)} 个岗位存在缺失信息或无效链接。完整指四列信息齐全且链接有效。` : '缺失信息会如实标记，不自动补全。';
    const chart = $('education-chart'); chart.replaceChildren();
    if (!stats.total) chart.append(element('p','chart-empty','采集完成后查看学历分布'));
    const entries = stats.distribution.slice(0,5);
    if (stats.distribution.length > 5) entries.push(['其他（其余学历原文）', stats.distribution.slice(5).reduce((sum,item) => sum + item[1],0)]);
    entries.forEach(([label,count]) => {
      const row = element('div', label === '未获取' ? 'chart-row missing' : 'chart-row');
      const header = element('div','chart-label');
      header.append(element('span','',label),element('strong','',`${number(count)} · ${percent(count,stats.total)}%`));
      const track = element('div','chart-track'), bar = element('span');
      bar.style.width = `${count / stats.total * 100}%`; track.append(bar); row.append(header,track); chart.append(row);
    });
  }
  function renderSource() {
    const result = state.resultTask;
    const context = !result ? '尚无采集结果' : `${historical() ? '历史结果' : '本次结果'} · ${shortID(result)}${testData(result) ? ' · HTML 测试' : ''}`;
    $('result-context').textContent = context;
    $('overview-context').textContent = `统计范围：${context}${historical() ? '（与本次采集进度分开）' : ''}`;
    $('source-badge').textContent = !result ? '待采集' : testData(result) ? 'HTML 测试样本' : historical() ? '历史结果' : '采集结果';
    $('source-file').textContent = result ? `任务 ${shortID(result)} · ${dateText(result.finished_at)}` : '尚无已保存结果';
    $('source-description').textContent = !result ? '固定访问原程序中的 Wayback Machine 招聘存档，每次任务独立保存。'
      : `${testData(result) ? '本地 HTML 测试样本，未访问真实招聘网站。' : '历史存档采集结果，招聘有效性未经核实。'}${historical() ? '当前列表、统计与下载均属于历史任务，本次任务未替换它。' : ''}下载包含该任务全部岗位，筛选仅影响页面展示。`;
  }
  function renderTask() {
    const task = state.task;
    const active = task && ACTIVE.has(task.status);
    $('start-button').disabled = !state.connected || state.starting || Boolean(active);
    $('start-button').textContent = state.starting ? '正在启动…' : active ? '采集中…' : '开始爬取 →';
    $('download-button').disabled = !state.connected || !state.resultTask?.result_ready || state.downloading;
    $('download-button').textContent = state.downloading ? '正在下载…' : historical() ? '↓ 下载历史 CSV' : state.resultTask ? '↓ 下载本次 CSV' : '↓ 下载 CSV';
    const connection = $('connection-indicator');
    connection.replaceChildren(element('span'), document.createTextNode(state.connected ? ' 本机服务已连接' : ' 服务未连接 · 状态待同步'));
    connection.classList.toggle('offline', !state.connected);
    $('reconnect-button').hidden = state.connected;
    $('task-status').textContent = task ? `${testData(task) ? 'HTML 测试 · ' : ''}${LABELS[task.status] || task.status}${!state.connected ? ' · 未同步' : ''}` : '尚未开始';
    $('task-id').textContent = task ? `本次任务 ${shortID(task)} · ${dateText(task.created_at)}` : '固定来源 · Wayback Machine';
    $('task-message').textContent = !state.connected ? '暂时无法连接后端，以下保留最近一次已确认的状态；连接恢复后自动同步。'
      : state.starting ? '正在请求后端创建任务…' : task ? `${task.current_job ? task.current_job + ' · ' : ''}${task.message}` : '点击“开始爬取”，由 Python 自动读取固定列表与岗位详情。';
    const progress = $('task-progress');
    if (task?.progress === null && active) progress.removeAttribute('value');
    else progress.value = task?.progress ?? 0;
    $('progress-label').textContent = task?.progress != null ? `${task.progress}%${!state.connected ? '（未同步）' : ''}` : active ? '列表总数未知' : '尚无岗位进度';
    $('task-discovered').textContent = task?.discovered == null ? '—' : number(task.discovered);
    $('task-processed').textContent = number(task?.processed || 0);
    $('task-parsed').textContent = number(task?.parsed || 0);
    $('task-failed').textContent = number(task?.failed || 0);
    $('task-detail').textContent = `${testData(task) ? '当前使用本地 HTML 测试样本，未访问真实网站。' : ''}${task ? `成功解析中，${task.complete} 个信息完整、${task.incomplete} 个字段不完整。` : ''}进度 = 已处理岗位 / 已发现岗位；失败岗位保留列表信息。`;
    $('task-error').hidden = !task?.error;
    $('task-error').textContent = task?.error || '';
    $('task-events').hidden = !task?.events?.length;
    const events = $('event-list'); events.replaceChildren();
    (task?.events || []).slice(-10).reverse().forEach(event => {
      events.append(element('li','',`${dateText(event.time)} · ${event.job ? event.job + ' · ' : ''}${event.message}`));
    });
    renderSource();
  }
  function populateEducation() {
    const select = $('education-filter'), previous = select.value;
    select.replaceChildren(new Option('全部学历',''));
    [...new Set(state.jobs.map(job => job.education).filter(Boolean))].sort((a,b) => a.localeCompare(b,'zh-CN')).forEach(value => select.add(new Option(value,value)));
    if ([...select.options].some(option => option.value === previous)) select.value = previous;
  }
  function statusBadge(job) {
    const complete = Data.complete(job);
    return element('span',`status-badge${complete ? '' : ' incomplete'}`,complete ? '信息完整' : '信息不完整');
  }
  function openDetail(job) {
    const badge = statusBadge(job); badge.id = 'detail-status'; $('detail-status').replaceWith(badge);
    $('detail-title').textContent = titleOf(job);
    $('detail-notice').textContent = testData(state.resultTask) ? '本地 HTML 测试样本，未从真实网站采集。' : '此记录来自历史网页存档，不代表当前招聘状态。';
    const fields = $('detail-fields'); fields.replaceChildren();
    const entries = [['学历要求',job.education || '未获取'],['专业要求',job.major || '未获取'],['原始链接',job.link || '未获取'],
      ['解析状态',job.parse_status === 'failed' ? `失败：${job.error || '未知原因'}` : '已解析'],
      ['所属结果',`${historical() ? '历史任务' : '本次任务'} ${shortID(state.resultTask)}${testData(state.resultTask) ? ' · 本地 HTML 测试' : ''}`]];
    entries.forEach(([key,value]) => fields.append(element('dt','',key),element('dd','',value)));
    const link = $('detail-link'); link.hidden = !job.url;
    if (job.url) link.href = job.url; else link.removeAttribute('href');
    $('job-dialog').showModal(); $('close-dialog').focus();
  }
  function renderRow(job) {
    const row = element('tr'), titleCell = element('td'), button = element('button','job-title-button');
    button.type = 'button'; button.setAttribute('aria-label',`查看岗位详情：${titleOf(job)}`);
    const icon = element('span','job-symbol','＋'); icon.setAttribute('aria-hidden','true');
    button.append(icon,element('span','job-title-text',titleOf(job)));
    button.addEventListener('click',() => openDetail(job)); titleCell.append(button);
    const educationCell = element('td'); educationCell.append(element('span',job.education ? 'education-tag' : 'missing-text',job.education || '未获取'));
    const majorCell = element('td'); majorCell.append(element('span','major-text',job.major || '未获取'));
    const statusCell = element('td'); statusCell.append(statusBadge(job));
    if (job.error) statusCell.title = job.error;
    const linkCell = element('td');
    if (job.url) {
      const link = element('a','external-link','↗');
      link.href = job.url; link.target = '_blank'; link.rel = 'noopener noreferrer';
      link.setAttribute('aria-label',`在新标签页打开 ${titleOf(job)} 的原始链接`); linkCell.append(link);
    } else linkCell.append(element('span','missing-text','—'));
    row.append(titleCell,educationCell,majorCell,statusCell,linkCell); return row;
  }
  function renderResults() {
    const total = state.filtered.length, pages = Math.max(1,Math.ceil(total / state.size));
    state.page = Math.min(state.page,pages);
    const start = (state.page - 1) * state.size;
    $('result-count').textContent = number(total);
    $('result-summary').textContent = state.resultTask ? `共 ${number(state.jobs.length)} 个岗位，匹配 ${number(total)} 个` : '等待采集完成后自动展示';
    $('table-wrap').hidden = !total; $('pagination').hidden = !total; $('empty-state').hidden = Boolean(total);
    const body = $('jobs-body'); body.replaceChildren();
    const fragment = document.createDocumentFragment();
    state.filtered.slice(start,start + state.size).forEach(job => fragment.append(renderRow(job))); body.append(fragment);
    const noMatch = state.jobs.length > 0;
    $('empty-title').textContent = noMatch ? '没有找到匹配的岗位' : state.task && ACTIVE.has(state.task.status) ? '正在采集历史岗位' : state.task?.error ? '本次采集未能获取结果' : '从一次采集开始';
    $('empty-description').textContent = noMatch ? '试试更短的关键词，或重置筛选条件查看全部岗位。' : state.task && ACTIVE.has(state.task.status) ? '真实进度显示在上方任务区域，完成后自动更新列表。' : state.task?.error ? '请查看上方失败原因，确认网络或存档可用后重新采集。' : '点击页面上方“开始爬取”，自动读取固定医院招聘存档。';
    $('empty-action').hidden = !noMatch;
    $('page-summary').textContent = `第 ${number(start + 1)}–${number(Math.min(start + state.size,total))} 项`;
    $('page-indicator').textContent = `${state.page} / ${pages}`;
    $('previous-page').disabled = state.page <= 1; $('next-page').disabled = state.page >= pages;
  }
  function applyFilters() { state.page = 1; state.filtered = Data.filterJobs(state.jobs,filters()); renderResults(); }
  function resetFilters() {
    ['title-search','major-search','education-filter','missing-filter'].forEach(id => { $(id).value = ''; });
    $('sort-select').value = 'original'; applyFilters();
  }
  async function loadResult(task) {
    const payload = await api(`/api/tasks/${task.id}/results`);
    const jobs = Data.normalizeJobs(payload.jobs);
    if (payload.task_id !== task.id || !payload.task.result_ready) throw new Error('后端结果与任务不匹配。');
    if ($('job-dialog').open) $('job-dialog').close();
    state.jobs = jobs; state.resultTask = payload.task;
    populateEducation(); applyFilters(); renderOverview();
  }
  async function synchronize() {
    if (state.starting) return;
    if (state.syncing) return state.syncing;
    state.syncing = (async () => {
      try {
        if (location.protocol === 'file:') throw new Error('请启动 FastAPI 后通过 http://127.0.0.1:8767/ 打开页面。');
        const overview = await api('/api/tasks');
        state.task = overview.active_task || overview.latest_task;
        if (overview.latest_result && overview.latest_result.id !== state.resultTask?.id) await loadResult(overview.latest_result);
        state.connected = true;
        if (state.syncError) message('服务连接已恢复，已重新核对真实任务状态。');
        state.syncError = false;
        const key = state.task ? `${state.task.id}:${state.task.status}` : '';
        if (state.task && !ACTIVE.has(state.task.status) && key !== state.notified) {
          state.notified = key;
          message(`${testData(state.task) ? '本地 HTML 测试 · ' : ''}任务 ${shortID(state.task)}：${state.task.error || state.task.message}${historical() ? ' 页面继续展示历史结果。' : ''}`, Boolean(state.task.error));
        }
      } catch (error) {
        state.connected = false;
        state.syncError = true;
        message(`服务同步失败：${error.message}。不会自动重发启动请求，连接恢复后将核对真实任务状态。`,true);
      } finally {
        renderTask();
        if (!state.jobs.length) renderResults();
      }
    })();
    try { await state.syncing; } finally { state.syncing = null; }
  }
  async function startTask() {
    if (state.starting || !state.connected || (state.task && ACTIVE.has(state.task.status))) return;
    state.starting = true; renderTask();
    try {
      if (state.syncing) await state.syncing;
      const task = await api('/api/tasks',{ method:'POST',headers:{'Content-Type':'application/json'},body:'{}' });
      state.task = task; $('feedback').hidden = true;
    } catch (error) {
      if (error.status === 409 && error.detail?.task) state.task = error.detail.task;
      if (!error.status) state.connected = false;
      message(`启动任务${error.status ? '失败' : '状态未确认'}：${error.message}。${!error.status ? '将先查询后端状态，避免重复启动。' : ''}`,true);
    } finally { state.starting = false; renderTask(); if (!state.jobs.length) renderResults(); }
  }
  async function downloadCSV() {
    if (!state.resultTask?.result_ready || state.downloading) return;
    const task = state.resultTask;
    state.downloading = true; renderTask();
    const controller = new AbortController(), timeout = setTimeout(() => controller.abort(),30000);
    try {
      const response = await fetch(`/api/tasks/${task.id}/download`,{cache:'no-store',signal:controller.signal});
      if (!response.ok) throw new Error((await response.json()).detail || `HTTP ${response.status}`);
      const url = URL.createObjectURL(await response.blob()), link = element('a');
      link.href = url; link.download = `招聘数据_${task.id}.csv`;
      document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url),1000);
      message(`已下载任务 ${shortID(task)} 的后端 CSV（全部 ${number(task.discovered)} 条岗位）。${testData(task) ? '这是本地 HTML 测试结果。' : ''}`);
    } catch (error) { message(`下载失败：${error.message}。请确认后端服务仍在运行。`,true); }
    finally { clearTimeout(timeout); state.downloading = false; renderTask(); }
  }

  let savedTheme;
  try { savedTheme = localStorage.getItem('hospital-archive-theme'); } catch { /* Optional preference. */ }
  function setTheme(theme) {
    document.documentElement.dataset.theme = theme;
    $('theme-label').textContent = theme === 'dark' ? '浅色模式' : '深色模式';
    $('theme-toggle').setAttribute('aria-label',`切换到${theme === 'dark' ? '浅色' : '深色'}主题`);
    $('theme-toggle').setAttribute('aria-pressed',String(theme === 'dark'));
    try { localStorage.setItem('hospital-archive-theme',theme); } catch { /* Optional preference. */ }
  }
  setTheme(['light','dark'].includes(savedTheme) ? savedTheme : matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  $('theme-toggle').addEventListener('click',() => setTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'));
  $('start-button').addEventListener('click',startTask);
  $('download-button').addEventListener('click',downloadCSV);
  $('reconnect-button').addEventListener('click',synchronize);
  $('empty-action').addEventListener('click',resetFilters);
  $('filter-form').addEventListener('submit',event => event.preventDefault());
  $('filter-form').addEventListener('input',applyFilters);
  $('filter-form').addEventListener('change',applyFilters);
  $('filter-form').addEventListener('reset',event => { event.preventDefault(); resetFilters(); });
  $('sort-select').addEventListener('change',applyFilters);
  $('page-size').addEventListener('change',() => { state.size = Number($('page-size').value); state.page = 1; renderResults(); });
  $('previous-page').addEventListener('click',() => { state.page--; renderResults(); });
  $('next-page').addEventListener('click',() => { state.page++; renderResults(); });
  $('close-dialog').addEventListener('click',() => $('job-dialog').close());
  $('job-dialog').addEventListener('click',event => {
    if (event.target !== $('job-dialog')) return;
    const rect = $('job-dialog').getBoundingClientRect();
    if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) $('job-dialog').close();
  });
  document.addEventListener('keydown',event => {
    if (event.key === '/' && !event.ctrlKey && !event.metaKey && !event.altKey && !$('job-dialog').open && !/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName)) {
      event.preventDefault(); $('title-search').focus();
    }
  });
  document.querySelectorAll('.nav-link').forEach(link => link.addEventListener('click',() => {
    document.querySelectorAll('.nav-link').forEach(item => item.classList.toggle('active',item === link));
  }));
  renderOverview(); renderTask(); renderResults();
  async function poll() { await synchronize(); setTimeout(poll,1000); }
  poll();
})();
