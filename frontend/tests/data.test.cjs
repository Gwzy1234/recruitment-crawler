const { test } = require('node:test');
const assert = require('node:assert/strict');
const Data = require('../data.js');
const jobs = Data.normalizeJobs([
  {title:'影像医师', education:'博士', major:'影像医学,临床医学', link:'https://example.com/1',parse_status:'parsed'},
  {title:'临床医师', education:'硕士及以上', major:'内科学', link:'https://example.com/2',parse_status:'parsed'},
  {title:'护理', education:'本科及以上', major:'none', link:'https://example.com/3',parse_status:'parsed'},
  {title:'助理', education:'NONE', major:'', link:'https://example.com/4',parse_status:'failed',error:'HTTP 404'},
  {title:'无链接岗位', education:'博士', major:'医学', link:'javascript:alert(1)',parse_status:'failed'}
]);
test('normalizes structured API results and none without inventing missing fields',() => {
  assert.equal(jobs[2].major,''); assert.equal(jobs[3].education,'');
  assert.equal(jobs[3].error,'HTTP 404'); assert.equal(jobs[4].url,'');
});
test('rejects malformed API payload instead of breaking rendering',() => {
  assert.throws(() => Data.normalizeJobs(null),/格式错误/);
  assert.throws(() => Data.normalizeJobs([null]),/格式错误/);
});
test('summary derives field coverage and completeness from actual records',() => {
  const stats=Data.summarize(jobs);
  assert.deepEqual([stats.total,stats.education,stats.major,stats.complete],[5,4,3,2]);
  assert.equal(stats.distribution.reduce((sum,item) => sum+item[1],0),5);
});
test('title, major, education and missing state combine with AND',() => {
  assert.equal(Data.filterJobs(jobs,{title:'医师',major:'医学',education:'博士',missing:'complete'}).length,1);
  assert.equal(Data.filterJobs(jobs,{title:' 不存在 '}).length,0);
});
test('all missing filters reflect normalized data and safe links',() => {
  for (const [missing,count] of [['incomplete',3],['education',1],['major',2],['both',1],['link',1],['complete',2]]) {
    assert.equal(Data.filterJobs(jobs,{missing}).length,count,missing);
  }
});
test('sorts remain stable and preserve source order',() => {
  const ids=jobs.map(job=>job.id);
  const asc=Data.filterJobs(jobs,{sort:'title-asc'}).map(job=>job.title);
  const desc=Data.filterJobs(jobs,{sort:'title-desc'}).map(job=>job.title);
  assert.deepEqual(asc,desc.reverse());
  assert.ok(Data.complete(Data.filterJobs(jobs,{sort:'complete'})[0]));
  assert.deepEqual(jobs.map(job=>job.id),ids);
});
test('HTML-looking fields remain plain strings and unsafe URLs are disabled',() => {
  const record=Data.normalizeJobs([{title:'<img src=x onerror=alert(1)>',link:'data:text/html,hi'}])[0];
  assert.match(record.title,/<img/); assert.equal(record.url,'');
  for (const url of ['file:///etc/passwd','javascript:1','https://user:pass@example.com','//example.com']) assert.equal(Data.safeURL(url),'');
});
test('empty dataset has honest zero counts',() => {
  assert.deepEqual(Data.summarize([]),{total:0,education:0,major:0,complete:0,distribution:[]});
});
