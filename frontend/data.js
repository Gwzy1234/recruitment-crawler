(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.HospitalData = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  function safeURL(value) {
    try {
      const url = new URL(value);
      return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password ? url.href : '';
    } catch { return ''; }
  }
  function normalizeJobs(jobs) {
    if (!Array.isArray(jobs)) throw new Error('后端结果格式错误：缺少岗位列表。');
    const clean = value => typeof value === 'string' && !/^none$/i.test(value.trim()) ? value.trim() : '';
    return jobs.map((job, index) => {
      if (!job || typeof job !== 'object') throw new Error('后端岗位记录格式错误。');
      const value = { id:index + 1, title:clean(job.title), education:clean(job.education), major:clean(job.major),
        link:clean(job.link), error:clean(job.error), parse_status:clean(job.parse_status) };
      value.url = safeURL(value.link);
      return value;
    });
  }
  // "完整" covers all four original CSV fields; links must be usable HTTP(S).
  const complete = job => Boolean(job.title && job.education && job.major && job.url);
  function summarize(jobs) {
    const education = jobs.filter(job => job.education).length;
    const major = jobs.filter(job => job.major).length;
    const distribution = new Map();
    jobs.forEach(job => {
      const label = job.education || '未获取';
      distribution.set(label, (distribution.get(label) || 0) + 1);
    });
    return { total: jobs.length, education, major, complete: jobs.filter(complete).length,
      distribution: [...distribution].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], 'zh-CN')) };
  }
  function filterJobs(jobs, filters = {}) {
    const title = (filters.title || '').trim().toLocaleLowerCase();
    const major = (filters.major || '').trim().toLocaleLowerCase();
    const result = jobs.filter(job => {
      if (!job.title.toLocaleLowerCase().includes(title) || !job.major.toLocaleLowerCase().includes(major)) return false;
      if (filters.education && job.education !== filters.education) return false;
      switch (filters.missing) {
        case 'incomplete': if (complete(job)) return false; break;
        case 'education': if (job.education) return false; break;
        case 'major': if (job.major) return false; break;
        case 'both': if (job.education || job.major) return false; break;
        case 'link': if (job.url) return false; break;
        case 'complete': if (!complete(job)) return false; break;
      }
      return true;
    });
    const sort = filters.sort || 'original';
    result.sort((a, b) => {
      if (sort === 'title-asc') return a.title.localeCompare(b.title, 'zh-CN') || a.id - b.id;
      if (sort === 'title-desc') return b.title.localeCompare(a.title, 'zh-CN') || a.id - b.id;
      if (sort === 'complete') return Number(complete(b)) - Number(complete(a)) || a.id - b.id;
      if (sort === 'education') return a.education.localeCompare(b.education, 'zh-CN') || a.id - b.id;
      return a.id - b.id;
    });
    return result;
  }
  return { complete, summarize, filterJobs, safeURL, normalizeJobs };
});
