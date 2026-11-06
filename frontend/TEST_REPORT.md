> 注意：此文档为之前独立后端版本的历史测试记录。2026-11-06 起正式 Web 后端改由 `team-task.py` 原始三个函数驱动，最新验证见 `../原始爬虫接入说明.md`。

# 第二阶段测试报告

日期：2026-11-03（Asia/Shanghai）。本地 HTML 样本验证与真实外部地址访问分开报告，数据没有混用。

## 检查结果

| 检查 | 结果 |
| --- | --- |
| Python 后端 unittest | 25 / 25 通过 |
| JavaScript 数据测试 | 8 / 8 通过 |
| Chrome → HTTP FastAPI → 本地 HTML → CSV | 12 个子检查通过；含父工作流的 Node 输出为 13 / 13 |
| JavaScript / Mac 启动脚本语法 | 通过 |
| `start.command` 启动正式服务 | 成功，`127.0.0.1:8767` |
| 正式页面 / 健康接口 | HTTP 200 |
| 正式页面恢复实际外网失败记录 | 失败状态、零岗位、禁用下载与可重试入口符合实际 |
| 1440 / 1024 / 768 / 390 / 320 px 布局 | 无页面横向溢出 |

环境：macOS、Python 3.14.7、Node.js 26.7.0、Chrome 156.0.8078.79。运行依赖：FastAPI 0.162.0、Uvicorn 0.54.0、requests 2.34.2、BeautifulSoup 4.15.0。测试使用 httpx 0.28.1 和宿主 Playwright。Starlette 对 httpx 测试适配发出弃用提示，当前测试正常通过。

## 本地 HTML 样本（不是真实招聘数据）

`web_backend/tests/fixtures/` 为本地编写样本，包含单双引号 UUID、专业逗号、缺失字段、404 详情、缺失 UUID、HTML 外观文本等。测试只替换外部请求，同一套解析、计数、文件保存、API 与前端代码实际运行。生产入口不导入此适配器。

主要样本实际解析出 12 个岗位，成功 10、失败 2；完整 9、字段不完整 1；学历非空 10、专业非空 9。浏览器统计一致。页面明确显示“HTML 测试样本，未访问真实招聘网站”。联调结果单独位于 `web_backend/tests/.artifacts/`，与正式数据隔离。

后端测试覆盖固定入口、UUID、详情标签、字段缺失、受限重定向、有限超时/5xx 重试、SSL/404、岗位失败隔离、中断、完整/部分完成、全部详情失败、列表结构异常、UTF-8-SIG 四列 CSV、引号与逗号、公式注入、下载门控、并发启动、文件锁、采集中其他请求可用、存储与初始化失败、历史保留、重启恢复、拒绝任意 URL/跨源表单以及静态白名单。

浏览器验证无上传/演示/网址输入、网页启动真正 HTTP 后台任务、禁用重复启动与后端 409、真实进度、自动展示、组合筛选与重置、排序分页、XSS 文本不执行、详情错误、Esc/焦点恢复与 `/`、后端下载逐字节比对、新任务失败时下载旧文件、本次/历史统计区分、采集中刷新恢复、断线恢复、主题与手机布局。

## 真实固定网址访问（未成功采集）

正式任务 `c346ad2e42a842b0a32fca72d0325330`：北京时间 2026-11-03 18:57:09 创建、18:57:13 失败。通过正式 `POST /api/tasks` 启动，实际使用 requests 请求原程序固定的 Wayback Machine URL。

结果为 SSL/TLS 连接失败，未获得列表。字段为 `discovered=null`、`processed=0`、`parsed=0`、`failed=0`、`progress=null`、`result_ready=false`，任务状态为 `failed`。失败岗位数 0 只说明尚无可逐项处理的岗位，不能解释为任务成功。

进一步 requests 诊断显示 `SSLEOFError: UNEXPECTED_EOF_WHILE_READING`，系统 curl 同一地址 15 秒后超时。证据指向连接/TLS 不可用，不能认定证书配置错误或存档不存在。没有关闭 TLS 验证、更换招聘来源或读取原 CSV/样本冒充本次结果。

正式目录只保存这次真实失败元信息，未生成 `results.csv` / `results.json`。正式浏览器已验证错误提示、零岗位、禁用下载和重试入口。真实成功采集、当前网站 HTML 结构及真实岗位内容需在网络可用后验证。

## 原始文件保护

目录中没有 `team-task(3).py`，没有创建、覆盖或重命名该文件。实际只读参考 `team-task.py`、`team_task_fixed.py`，未 import 或执行旧脚本。

开发前记录 `frontend/` 外原有 1,185 个文件的路径、大小及修改时间，最终核对全部一致；两份主程序与原 CSV 的 SHA-256 也一致。其他文件核对的是大小和修改时间，未逐一读取内容做哈希。

```text
team-task.py
c49f58fb66ed69d06153466a6beeebba34f9ee08d569566a6a4583be958691ab

team_task_fixed.py
5e5beded87fc83d3d2561247208f269a7f809bf6818376922b88067d9a99eddd

招聘数据.csv
008996b0e079cffaf5d23fb0860b9ad543c76db1f484fde9d555892cd0604c6b
```

变更仅限第一阶段 `frontend/` 与新建的 `web_backend/`。原始 CSV 和项目原有 `.venv/` 未修改。

## 截图与限制

`tests/artifacts/phase2-live-connection-failure.png` 是正式服务的真实失败记录。其他 `*-html-test.png` 为明确标注的本地样本，含采集中、完成、历史、手机、深色主题。已视觉检查桌面与手机布局。

未实机验收 Safari、Firefox、真实手机或屏幕阅读器。服务限定单机单进程，未实现账号、任务取消按钮、分布式队列或数据库。历史任务保存在 JSON 并可经 API 查询；前端自动恢复最近保存结果，未新增完整历史管理页。
