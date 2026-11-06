/* Real browser -> real HTTP FastAPI -> local HTML fixture adapter -> real stored CSV.
   No production website success is claimed by this suite. Start fixture_server first. */
const { test }=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const baseURL=process.env.BASE_URL || 'http://127.0.0.1:8766/';
const artifacts=path.join(__dirname,'artifacts');

test('phase 2 HTTP integration with explicitly LOCAL HTML TEST data',{timeout:120000},async t=>{
  fs.mkdirSync(artifacts,{recursive:true});
  const browser=await chromium.launch({channel:'chrome',headless:true});
  const context=await browser.newContext({viewport:{width:1440,height:1000},colorScheme:'light',reducedMotion:'reduce',acceptDownloads:true});
  const page=await context.newPage();
  const errors=[]; page.on('pageerror',error=>errors.push(error.message));
  const waitText=(id,text)=>page.waitForFunction(({id,text})=>document.getElementById(id).textContent.includes(text),{id,text});
  const shot=async name=>{
    await page.evaluate(()=>window.scrollTo({top:0,behavior:'instant'}));
    await page.screenshot({path:path.join(artifacts,name),fullPage:true,animations:'disabled'});
  };
  let firstId, thirdId, csv;
  try {
    await page.goto(baseURL);
    await t.test('initial API connection, no upload/demo/URL input, download disabled',async()=>{
      await page.locator('#start-button').waitFor({state:'visible'});
      await page.waitForFunction(()=>!document.getElementById('start-button').disabled);
      assert.equal(await page.locator('input[type=file], #demo-button, #import-button, #drop-zone').count(),0);
      assert.equal(await page.locator('input[type=url]').count(),0);
      assert.ok(await page.locator('#download-button').isDisabled());
      assert.equal(await page.locator('#stat-total').textContent(),'0');
      await shot('phase2-empty.png');
    });
    await t.test('button starts a real backend task, exposes true progress and rejects duplicate',async()=>{
      const started=page.waitForResponse(response=>response.url().endsWith('/api/tasks') && response.request().method()==='POST');
      await page.locator('#start-button').click();
      const result=await started; assert.equal(result.status(),202);
      firstId=(await result.json()).id;
      assert.ok(await page.locator('#start-button').isDisabled());
      assert.ok(await page.locator('#download-button').isDisabled());
      const duplicate=await context.request.post(new URL('api/tasks',baseURL).href,{data:{}});
      assert.equal(duplicate.status(),409);
      await waitText('task-discovered','12');
      await waitText('task-status','HTML 测试');
      const status=await (await context.request.get(new URL(`api/tasks/${firstId}`,baseURL).href)).json();
      assert.equal(status.source_kind,'local_html_test');
      assert.equal(status.progress,Math.floor(status.processed*100/status.discovered));
      assert.ok(status.processed<12);
      await shot('phase2-progress-html-test.png');
    });
    await t.test('task completion auto-renders fixture results and exact counters',async()=>{
      await waitText('stat-total','12');
      await waitText('task-status','部分完成');
      assert.equal(await page.locator('#task-parsed').textContent(),'10');
      assert.equal(await page.locator('#task-failed').textContent(),'2');
      assert.equal(await page.locator('#stat-education').textContent(),'10');
      assert.equal(await page.locator('#stat-major').textContent(),'9');
      assert.equal(await page.locator('#stat-complete').textContent(),'9');
      assert.equal(await page.locator('#jobs-body tr').count(),10);
      assert.match(await page.locator('#source-badge').textContent(),/HTML 测试/);
      assert.ok(!(await page.locator('#download-button').isDisabled()));
      await shot('phase2-results-html-test.png');
    });
    await t.test('search, combined filters, no-result reset and sorting still work',async()=>{
      await page.locator('#title-search').fill('影像');
      await page.locator('#major-search').fill('核医学');
      await page.locator('#education-filter').selectOption('博士');
      await page.locator('#missing-filter').selectOption('complete');
      assert.equal(await page.locator('#result-count').textContent(),'1');
      assert.equal(await page.locator('#stat-total').textContent(),'12');
      await page.locator('#title-search').fill('不存在');
      assert.ok(await page.locator('#empty-action').isVisible());
      // Download is a saved full-task CSV, so filtering never disables it.
      assert.ok(!(await page.locator('#download-button').isDisabled()));
      await page.locator('#empty-action').click();
      assert.equal(await page.locator('#result-count').textContent(),'12');
      await page.locator('#sort-select').selectOption('title-asc');
      const names=await page.locator('.job-title-text').allTextContents();
      assert.deepEqual(names,[...names].sort((a,b)=>a.localeCompare(b,'zh-CN')));
      await page.locator('#reset-button').click();
    });
    await t.test('pagination and page size preserve the complete dataset',async()=>{
      await page.locator('#next-page').click(); assert.equal(await page.locator('#jobs-body tr').count(),2);
      await page.locator('#page-size').selectOption('20'); assert.equal(await page.locator('#jobs-body tr').count(),12);
    });
    await t.test('API-provided HTML stays inert and details preserve failure reasons',async()=>{
      assert.equal(await page.locator('#jobs-body img, #jobs-body script').count(),0);
      await page.locator('.job-title-button').filter({hasText:'<img'}).click();
      assert.equal(await page.locator('#detail-title img').count(),0);
      assert.match(await page.locator('#detail-notice').textContent(),/测试样本/);
      await page.keyboard.press('Escape');
      const failed=page.locator('.job-title-button').filter({hasText:'存档缺失'});
      await failed.click();
      assert.match(await page.locator('#detail-fields').textContent(),/404/);
      assert.equal(await page.locator('#detail-link').getAttribute('target'),'_blank');
      assert.equal(await page.locator('#detail-link').getAttribute('rel'),'noopener noreferrer');
      await page.keyboard.press('Escape');
      assert.ok(await failed.evaluate(node=>node===document.activeElement));
      await page.locator('h1').click(); await page.keyboard.press('/');
      assert.ok(await page.locator('#title-search').evaluate(node=>node===document.activeElement));
    });
    await t.test('download requests backend generated CSV with BOM and four columns',async()=>{
      const request=page.waitForRequest(req=>req.url().endsWith(`/api/tasks/${firstId}/download`));
      const pending=page.waitForEvent('download'); await page.locator('#download-button').click();
      await request; const download=await pending; csv=fs.readFileSync(await download.path());
      assert.deepEqual([...csv.subarray(0,3)],[239,187,191]);
      assert.ok(csv.toString('utf8').startsWith('\uFEFF岗位名,学历,专业,链接\r\n'));
      const direct=await context.request.get(new URL(`api/tasks/${firstId}/download`,baseURL).href);
      assert.deepEqual(csv,await direct.body());
      assert.match(download.suggestedFilename(),new RegExp(firstId));
    });
    await t.test('new failed task retains visibly historical result and original download',async()=>{
      await page.locator('#start-button').click();
      await waitText('result-context','历史结果');
      assert.match(await page.locator('#overview-context').textContent(),/历史结果/);
      assert.match(await page.locator('#download-button').textContent(),/历史 CSV/);
      await waitText('task-status','任务失败');
      assert.match(await page.locator('#task-error').textContent(),/404/);
      assert.equal(await page.locator('#stat-total').textContent(),'12');
      assert.equal(await page.locator('#task-parsed').textContent(),'0');
      const latest=await (await context.request.get(new URL('api/tasks',baseURL).href)).json();
      assert.equal(latest.latest_result.id,firstId);
      const pending=page.waitForEvent('download'); await page.locator('#download-button').click();
      assert.deepEqual(fs.readFileSync(await (await pending).path()),csv);
      await shot('phase2-failed-with-history-html-test.png');
    });
    await t.test('reload during another task reconnects without starting a duplicate',async()=>{
      const started=page.waitForResponse(response=>response.url().endsWith('/api/tasks')&&response.request().method()==='POST');
      await page.locator('#start-button').click(); thirdId=(await (await started).json()).id;
      await page.reload(); await waitText('task-id',thirdId.slice(0,8));
      assert.ok(await page.locator('#start-button').isDisabled());
      assert.match(await page.locator('#result-context').textContent(),/历史结果/);
      await page.waitForFunction(id=>document.getElementById('result-context').textContent.includes(id),thirdId.slice(0,8));
      await waitText('task-status','部分完成');
      assert.match(await page.locator('#result-context').textContent(),/本次结果/);
    });
    await t.test('API loss preserves results and disables start; reconnect restores state',async()=>{
      await page.route('**/api/tasks',route=>route.abort('failed'));
      await waitText('connection-indicator','未连接');
      assert.ok(await page.locator('#start-button').isDisabled());
      assert.equal(await page.locator('#stat-total').textContent(),'12');
      assert.ok(await page.locator('#reconnect-button').isVisible());
      await page.unroute('**/api/tasks'); await page.locator('#reconnect-button').click();
      await waitText('connection-indicator','已连接');
      assert.doesNotMatch(await page.locator('#feedback').textContent(),/服务同步失败/);
    });
    await t.test('320–1440 px responsive layout, themes and result persistence across reload',async()=>{
      await page.locator('#page-size').selectOption('10');
      for(const width of [1440,1024,768,390,320]){
        await page.setViewportSize({width,height:900});
        assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`overflow at ${width}`);
        if(width===390)await shot('phase2-mobile-html-test.png');
      }
      await page.setViewportSize({width:1440,height:1000});
      await page.locator('#theme-toggle').click(); await shot('phase2-dark-html-test.png');
      await page.reload(); await waitText('stat-total','12');
      assert.equal(await page.locator('html').getAttribute('data-theme'),'dark');
    });
    await t.test('no uncaught JavaScript errors',()=>assert.deepEqual(errors,[]));
  }finally{await browser.close();}
});
