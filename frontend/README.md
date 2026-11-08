# 医院招聘信息检索与可视化平台 · 第二阶段

保留第一阶段的界面、浅深主题、响应式布局、统计、搜索筛选、排序、分页和详情弹窗，改为 **FastAPI + 独立 Python 爬虫 + 原生 JavaScript**。不再上传或导入 CSV，不提供网址输入框或演示按钮。

## Mac 本地启动

需要 Python 3.10 或更新版本；本机已用 Python 3.14.7 验证：


## 本地启动

需要 Python 3.11 或更高版本。

请先将项目完整解压，然后进入项目根目录。

- Windows：双击 `start.bat`
- macOS：双击 `start.command`，或执行 `bash start.sh`
- Linux：执行 `bash start.sh`

启动器会自动创建根目录下的 `.runtime` 虚拟环境，并根据 `web_backend/requirements.txt` 安装依赖。

首次安装依赖需要网络连接，无需安装 Node.js。

启动成功后访问：

http://127.0.0.1:8767/

页面和 API 均由 FastAPI 提供，不需要额外启动静态服务器。

若端口被占用，可执行：

```bash
PORT=8768 bash start.sh
```

在终端按 `Ctrl+C` 停止服务。


也可以在 Finder 双击 `web_backend/start.command`。首次缺少依赖时，脚本仅在新建的 `web_backend/.venv/` 安装 `web_backend/requirements.txt`，不修改项目原有 `.venv/`。

打开 <http://127.0.0.1:8767/>。**页面和 API 都由 FastAPI 提供，不再使用第一阶段的 `python -m http.server` 或直接双击 HTML。** 本次使用 8767 避开本机已占用的 8765；旧静态服务器没有采集 API。按 `Ctrl+C` 停止服务，正在请求的网页返回或超时后退出。

手动安装与启动方式：

```sh
python3 -m venv web_backend/.venv
web_backend/.venv/bin/python -m pip install -r web_backend/requirements.txt
web_backend/.venv/bin/python -m uvicorn web_backend.app:app --host 127.0.0.1 --port 8767 --workers 1
```

端口被占用可用 `PORT=8768 ./web_backend/start.command`。服务仅绑定回环地址，使用单进程，不加 `--reload`。爬虫运行于独立线程，不阻塞页面与状态查询。

## 使用流程

1. 打开页面，自动连接后端，恢复最近任务和最近一份已保存结果。首次运行没有自动填充的样例数据。
2. 点击“开始爬取”，Python 访问固定 Wayback Machine 招聘列表，从 `onclick` 第一段引号内容提取 UUID，构造详情 URL，逐个解析学历与专业。
3. 任务区域展示真实状态、发现/处理/解析/失败数量，以及最近实际请求事件。列表还未解析时总数显示“—”，不捏造百分比。
4. 采集结束且保存成功后，自动更新列表与统计。详情失败的岗位保留列表信息，学历/专业标为未获取；详情弹窗可查看错误原因。
5. 点击“下载本次 CSV”，直接请求后端已生成文件。编码为 UTF-8-SIG，表头为 `岗位名,学历,专业,链接`，标准引号处理逗号和换行，缺失值写为 `none`。

启动中与采集中禁止重复操作，后端也拒绝并发任务。刷新页面只查询状态，不会再次启动采集。

**下载包含所属任务的全部岗位，不是筛选子集。** 关键词、学历、缺失状态、排序和分页仅影响页面展示。为避免 Excel 执行外部文本公式，前导 `= + - @` 的字段在 CSV 中加单引号；JSON 展示保留原文。

## 本次任务与历史结果

新任务执行期间，上一份已保存结果仍可查看和下载。统计范围、结果标签、来源卡片和下载按钮均标明“历史结果”及任务编号；本次进度和数量单独展示。

本次保存成功后自动切换结果。本次列表请求失败、保存失败或任务中断时，不替换历史结果；没有历史结果则下载始终禁用。断线时保留最近确认状态并标注“未同步”，恢复后重新核对后端，不自动重发启动请求。

## 固定来源与统计口径

固定入口是原程序中的：

```text
https://web.archive.org/web/20260515165600/https://zp.z2hospital.com/department/detailInfomore.action
```

这是**历史网页存档，不代表当前在招**。存档时间不是岗位发布时间或采集时间。未补造医院、地区、薪资、发布时间等原程序未提供的字段。

- 已发现：实际找到的 `li.zp_li` 数量，包含缺名称/UUID 的错误记录。
- 已处理 = 成功解析 + 失败，岗位请求/解析完成或确定失败时才增加。
- 成功解析：详情有可识别学历/专业字段，允许其中字段缺失。
- 信息完整：名称、学历、专业、有效链接均齐全；成功解析 = 完整 + 字段不完整。
- 进度为 `已处理 / 已发现 × 100%` 向下取整。100% 表示岗位处理结束，文件保存另有状态。
- 失败岗位为逐项请求/解析或列表记录失败。列表整体失败时总数未知，不捏造失败岗位数。
- 总览和分布基于当前展示的整份结果，搜索匹配数独立计算。学历保留原文，最多显示 5 个标签，其余明确汇总为“其他”。

HTTP 200 但没有岗位结构也判为解析失败，不伪装成正常空结果。列表失败不生成“空成功 CSV”。

## 文件结构与作用

```text
frontend/
├── index.html                 # 现有页面，增加采集任务区
├── styles.css                 # 原主题与响应式布局，增加任务样式
├── app.js                     # REST 调用、轮询、渲染和后端下载
├── data.js                    # 复用统计、筛选、排序与安全规范化
├── README.md
├── TEST_REPORT.md
└── tests/
    ├── data.test.cjs          # 无第三方依赖的数据测试
    ├── browser.test.cjs       # 浏览器 → API → HTML 样本 → CSV 联调
    └── artifacts/             # 明确标识来源的测试截图
web_backend/
├── app.py                     # FastAPI、同源接口与静态白名单
├── collector.py               # 固定源 requests / BeautifulSoup 适配
├── tasks.py                   # 单任务锁、事件计数、保存与恢复
├── start.command              # Mac 启动脚本，可设置 PORT
├── requirements.txt           # 四个已验证运行依赖
├── README.md
├── __init__.py
├── .gitignore
├── .venv/                     # 独立运行环境
├── data/<task-id>/            # 正式任务数据
│   ├── task.json              # 状态、计数、错误和最近 100 个事件
│   ├── results.json           # 保存成功后可读取，含逐岗位错误
│   └── results.csv            # 保存成功后可下载，UTF-8-SIG
└── tests/                     # 后端测试、本地 HTML 和独立测试服务
```

第一阶段的 `csv.js`、`sample.csv`、旧 CSV 测试和旧演示截图已移除，没有隐藏上传功能。未增加数据库或前端框架。

## 原文件保护

实际目录没有 `team-task(3).py`；只读参考现有 `team-task.py`、`team_task_fixed.py`，没有运行或 import 旧脚本。所有原 Python 文件、原始 `招聘数据.csv` 及原有 `.venv/` 保持不变，不使用旧脚本的绝对输出路径。改动仅限允许调整的 `frontend/` 与新建的 `web_backend/`。

结果使用独立 UUID 目录、排他创建和写完后改名，完成前不开放下载。原文件校验见 [测试报告](TEST_REPORT.md)。

## 测试与尚未验证范围

API 及测试命令见 [后端说明](../web_backend/README.md)，结果见 [TEST_REPORT.md](TEST_REPORT.md)。本地 HTML 联调页面会标明“HTML 测试样本”，数据与正式目录隔离。

本次真实固定网址访问失败：requests 遇到 TLS 连接提前关闭（`UNEXPECTED_EOF_WHILE_READING`），系统 curl 也在 15 秒后超时。正式服务保留真实失败记录，没有真实岗位结果或 CSV；没有关闭 TLS 验证、切换来源或用原 CSV/样本冒充本次结果。需要在存档可访问的网络下再次采集，才能验证当前网站结构与真实全程采集。

服务面向单机单进程，未实现账号、任务取消按钮、分布式队列、跨设备访问或完整历史任务管理页；历史记录已保存在 JSON 并可从 API 查询。已做 Chrome 自动化及手机尺寸检查，Safari、Firefox、真实手机和屏幕阅读器未实机验收。
