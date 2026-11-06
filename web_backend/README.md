# 固定招聘存档爬虫后端

FastAPI 同时提供页面与 REST API，requests / BeautifulSoup 在独立工作线程中采集。默认监听 `127.0.0.1:8767`。不 import 或执行原脚本，不接受用户提供的爬取 URL。

项目根目录运行 `./web_backend/start.command`，打开 <http://127.0.0.1:8767/>。安装说明见 [前端 README](../frontend/README.md)。只启动一个服务，不需要静态服务器。

## 接口

| 方法与路径 | 行为 |
| --- | --- |
| `GET /api/health` | 服务状态与固定列表地址 |
| `POST /api/tasks` | JSON 请求体只能为 `{}`；返回 202 和任务记录 |
| `GET /api/tasks?limit=20` | 活动任务、最新任务、最新已保存结果和最近任务列表（最多 100） |
| `GET /api/tasks/{id}` | 状态、真实计数、事件、错误、结果是否可用 |
| `GET /api/tasks/{id}/results` | 指定已保存任务的结构化结果 |
| `GET /api/results/latest` | 最近保存的结果；新失败任务不覆盖旧结果 |
| `GET /api/tasks/{id}/download` | 下载指定任务后端生成的 UTF-8-SIG CSV |

无任务为 404；运行中获取结果/下载、重复启动为 409；非法启动字段为 422；跨源启动为 403；非 JSON 启动为 415。任务 ID 仅允许 32 位十六进制 UUID，不接受文件路径。静态白名单仅暴露首页与三个必需资源，不暴露原项目或数据目录。

真实采集启动示例（会访问外部固定网站，仅在需要时执行）：

```sh
curl -H 'Content-Type: application/json' -d '{}' http://127.0.0.1:8767/api/tasks
```

任务字段：`id/status/source_url/source_kind/created_at/started_at/finished_at/discovered/processed/parsed/failed/complete/incomplete/progress/current_job/message/error/events/result_ready/download_url`。正式来源是 `wayback`，仅测试适配器为 `local_html_test`；生产接口或环境变量不提供测试模式。

结果结构为 `{task_id, source_url, source_kind, task, jobs:[{id,title,education,major,link,parse_status,error}]}`。缺失字段在 JSON 为空字符串、CSV 为 `none`。解析状态为 `parsed` 或 `failed`。

## 任务、计数与持久保存

生命周期为 `queued → fetching_list → fetching_details → saving → completed / partial`，整体请求/解析/存储失败为 `failed`，服务停止或上次未完成的任务为 `interrupted`。

详情失败或字段不完整时为 `partial`，可下载保留原列表信息的 CSV；全部详情失败时也如实显示解析成功 0，不把文件生成等同于采集成功。列表未解析时总数和百分比未知；仅每个岗位实际处理结束时增加进度。

数据保存在模块旁的 `data/<task-id>/`，不依赖旧绝对路径或命令当前目录。任务元信息原子更新，新 CSV/JSON 在独立目录中排他创建，写完后改名；只有两份结果和完成状态都写入才开放下载。失败任务保留错误，`.part` 临时文件不会作为结果返回。

进程内锁与 `fcntl.flock` 限制一个采集器。服务仍用 `--workers 1`，不要同时启动多个实例共用数据目录；文件锁不是多进程共享状态总线。历史元信息由 JSON 恢复，不需要数据库。

连接/读取超时为 5/15 秒；超时、连接错误、429、部分 5xx 最多重试一次，SSL 与 404 不重试；最多跟随 5 次重定向，且目标仅限固定医院路径的 HTTPS Wayback 地址。详情请求间隔 1 秒。未关闭 TLS 校验。

## 测试

在项目根目录运行，本地 HTML 测试不访问真实招聘网站：

```sh
web_backend/.venv/bin/python -m pip install -r web_backend/tests/requirements.txt
web_backend/.venv/bin/python -m unittest web_backend.tests.test_backend -v
node --test frontend/tests/data.test.cjs
```

浏览器联调需要 Chrome 和 Playwright，仅为测试工具。第一个终端启动明确标注的本地 HTML 测试服务，每次重启并使用新的数据目录：

```sh
web_backend/.venv/bin/python -m web_backend.tests.fixture_server \
  --port 8766 --data-dir "web_backend/tests/.artifacts/browser-$(date +%s)"
```

第二个终端：

```sh
BASE_URL=http://127.0.0.1:8766/ node --test frontend/tests/browser.test.cjs
```

若 Playwright 不在默认模块路径，可设 `PLAYWRIGHT_MODULE=/绝对路径/playwright`。本次使用宿主已有的 Playwright，没有给生产前端添加依赖。

样本服务按顺序提供：第一次本地 HTML 部分成功、第二次列表 HTTP 404、第三次再次处理样本。外部响应被显式替换，但进度仍来自实际解析事件；页面、API 来源字段与测试目录均有区别，不冒充真实采集。联调通过真实 HTTP 连接浏览器、FastAPI、工作线程、解析、文件保存和下载。测试后按 `Ctrl+C` 停止 8766，它与正式 8767 的数据隔离。

## 真实访问情况

2026-11-03 正式任务访问固定网址失败于 TLS 连接，未得到列表，未生成 CSV。进一步 requests 诊断为 TLS EOF，系统 curl 也超时。已验证外网错误处理与本地 HTML 全流程，没有宣称真实招聘采集成功。网络恢复后可直接从正式页面重试，无需更换来源或关闭证书验证。
