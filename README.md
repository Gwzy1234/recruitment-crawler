# 医院招聘信息采集与可视化系统

## 1. 项目简介

本项目为 Python 语言程序设计课程项目，使用 FastAPI、Requests、BeautifulSoup 和原生 HTML/CSS/JavaScript，实现招聘信息采集、任务状态展示、结果筛选、统计分析及 CSV 下载。

系统使用固定的医院招聘历史网页存档作为采集来源，主要用于课程学习和技术演示。历史网页信息不代表当前招聘情况。

## 2. 项目结构

| 文件或目录 | 主要作用 |
|---|---|
| `frontend/` | 网页界面、数据展示与交互 |
| `web_backend/app.py` | FastAPI 服务及接口 |
| `web_backend/collector.py` | 网页请求与岗位信息解析 |
| `web_backend/tasks.py` | 采集任务管理与结果保存 |
| `web_backend/requirements.txt` | Python 运行依赖 |
| `web_backend/tests/` | 后端测试及本地 HTML 测试样本 |
| `launch.py` | 自动准备环境和启动服务 |
| `start.bat` | Windows 启动入口 |
| `start.command` | macOS 启动入口 |
| `start.sh` | macOS/Linux 启动脚本 |
| `team-task.py` | 保留的原始独立爬虫程序 |
| `compose.yaml` | Docker Compose 配置 |
| `DEPLOY.md` | 服务器部署说明 |

## 3. 环境要求

- Python 3.11 或更高版本
- Windows、macOS 或 Linux
- 首次安装依赖需要网络连接
- 无需安装 Node.js 或独立数据库

主要 Python 依赖为 FastAPI、Uvicorn、Requests 和 BeautifulSoup4，具体版本以 `web_backend/requirements.txt` 为准。

## 4. 安装与启动

从 GitHub 下载源码并解压至本地文件夹。

项目地址：

https://github.com/Gwzy1234/recruitment-crawler

**Windows：** 双击根目录下的 `start.bat`。

**macOS：** 双击根目录下的 `start.command`，或在项目根目录执行：

```bash
bash start.sh
```

**Linux：** 在项目根目录执行：

```bash
bash start.sh
```

启动脚本将自动创建 `.runtime` 虚拟环境，并安装 `web_backend/requirements.txt` 中的运行依赖。

安装完成后，访问：

http://127.0.0.1:8767/

如浏览器未自动打开，可手动输入该地址。

关闭程序时，在启动终端按 `Ctrl+C`。

若默认端口被占用，可使用 `PORT` 参数修改端口，例如：

```bash
PORT=8768 bash start.sh
```

## 5. 使用方法

启动后，打开系统首页，点击“开始爬取”创建采集任务。系统将请求固定数据源，解析岗位名称、学历、专业及详情链接。

页面可显示采集进度、成功及失败数量，并提供关键词搜索、筛选、排序、分页和岗位详情查看。

采集结果成功保存后，可下载 CSV 文件。采集失败时，系统显示错误信息，不使用虚构数据替代真实采集结果。

## 6. 数据源说明

系统固定使用浙江大学医学院附属第二医院招聘网页的 Wayback Machine 历史存档：

https://web.archive.org/web/20260515165600/https://zp.z2hospital.com/department/detailInfomore.action

该网址属于 2026 年 5 月 15 日的历史网页存档，不能代表当前招聘信息。

数据请求和解析由 `web_backend/collector.py` 完成。系统不提供任意采集网址输入功能。

外部历史存档可能因网络、服务可用性或页面结构变化而采集失败。

## 7. 配置与输出

本地启动默认使用 `127.0.0.1:8767`，可通过 `PORT` 环境变量调整端口。

`.env.example` 主要用于 Docker 和 Cloudflare Tunnel 部署，本地一键启动无需配置 Cloudflare Token。

每次任务的数据默认保存在：

`web_backend/data/<task-id>/`

其中：

| 文件 | 内容 |
|---|---|
| `task.json` | 任务状态、统计数量、错误与事件记录 |
| `results.json` | 结构化岗位采集结果 |
| `results.csv` | 可供下载的岗位信息 |

CSV 采用 UTF-8-SIG 编码，包含岗位名、学历、专业和链接四列。

未成功生成结果的任务可能只有状态文件。源码压缩包不包含实际历史采集数据。

## 8. 测试与注意事项

`web_backend/tests/fixtures/` 提供本地 HTML 测试样本，用于检查网页解析与后端处理逻辑，不属于真实招聘数据。

历史测试记录见 `frontend/TEST_REPORT.md`，后端接口和测试方法见 `web_backend/README.md`。

本项目仅用于教学和课程演示。使用采集结果时，应保留数据来源说明，不得将历史存档岗位宣传为当前正在招聘的岗位。

服务器及 Docker 部署方案参见 `DEPLOY.md`，其配置和外部访问限制与本地运行方式有所不同。