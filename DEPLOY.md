# 医院招聘信息采集系统部署说明

## 1. 部署概述

本项目为基于 Python 的医院招聘信息采集与可视化系统，采用 FastAPI 提供后端接口及网页服务，使用 Requests 和 BeautifulSoup 完成招聘网页请求与信息解析。

项目支持 Windows、macOS 和 Linux 本地运行，也提供基于 Docker Compose 的 Ubuntu 服务器部署方案。

本文档主要介绍 Ubuntu 24.04 环境下的 Docker 部署、运行检查、Cloudflare Tunnel 配置及数据维护方法。普通电脑本地运行请参考项目根目录 `README.md`。

### 1.1 技术架构

| 组成 | 技术或文件 | 主要作用 |
|---|---|---|
| 前端 | HTML、CSS、JavaScript | 网页展示与用户交互 |
| 后端 | FastAPI、Uvicorn | 页面服务及 REST API |
| 采集模块 | `web_backend/collector.py` | 固定数据源请求与解析 |
| 任务模块 | `web_backend/tasks.py` | 采集任务管理与结果保存 |
| 数据存储 | JSON、CSV | 保存任务记录和采集结果 |
| 容器部署 | Docker Compose | 服务构建、运行与数据持久化 |
| 远程访问 | Cloudflare Tunnel | 可选的 HTTPS 访问方案 |

系统不依赖 MySQL、PostgreSQL 等独立数据库服务，任务状态和采集结果以文件形式保存。

前端页面与后端 API 由同一个 FastAPI 服务提供，无需单独部署 Nginx 或前端开发服务器。

### 1.2 数据采集流程

系统按照以下流程执行采集任务：

1. 用户通过网页创建采集任务。
2. FastAPI 接收请求，由任务管理模块创建任务记录。
3. `collector.py` 请求固定的招聘网页历史存档。
4. BeautifulSoup 解析岗位列表，并逐项获取岗位详情。
5. 任务管理模块更新采集进度、成功及失败数量。
6. 采集结束后保存 JSON、CSV 结果，网页提供查询与下载功能。

项目保留 `team-task.py` 等原始独立脚本作为代码参考。当前网页系统实际使用 `web_backend/collector.py`，不直接调用这些原始脚本。

## 2. 部署环境

推荐服务器环境：

| 项目 | 要求 |
|---|---|
| 操作系统 | Ubuntu 24.04 LTS |
| 容器运行环境 | Docker Engine |
| 容器编排 | Docker Compose V2 |
| 容器内 Python | Python 3.11 |
| 代码来源 | GitHub 公开仓库 |
| 网络 | 首次构建镜像需连接网络 |

项目仓库：

https://github.com/Gwzy1234/recruitment-crawler

使用 Docker 部署时，Python 及项目依赖在构建镜像过程中自动安装，宿主机无需单独配置 Python 虚拟环境。

部署前执行：

```bash
docker --version
docker compose version
git --version
```

确认 Docker、Docker Compose 和 Git 已正确安装。

## 3. 获取项目代码

在 Ubuntu 终端执行：

```bash
cd ~
git clone https://github.com/Gwzy1234/recruitment-crawler.git
cd recruitment-crawler
```

如果已经下载过项目，进入原项目目录即可：

```bash
cd ~/recruitment-crawler
```

确认以下部署文件存在：

```text
recruitment-crawler/
├── .env.example
├── Dockerfile
├── compose.yaml
├── DEPLOY.md
├── frontend/
└── web_backend/
    ├── app.py
    ├── collector.py
    ├── tasks.py
    └── requirements.txt
```

`Dockerfile` 负责创建 Python 运行镜像，`compose.yaml` 定义 Web 服务、Cloudflare Tunnel 服务及持久化数据卷。

## 4. 配置运行参数

项目根目录提供 `.env.example` 作为环境变量配置示例。

执行：

```bash
cp .env.example .env
nano .env
```

配置内容示例：

```dotenv
PUBLIC_HOSTNAME=jobs.example.com
LOCAL_PORT=18083
CF_TUNNEL_TOKEN=REPLACE_WITH_NEW_TUNNEL_TOKEN
```

主要参数说明：

| 参数 | 作用 |
|---|---|
| `PUBLIC_HOSTNAME` | 预留的 Cloudflare 公网域名配置 |
| `LOCAL_PORT` | 宿主机本地访问端口，默认 18083 |
| `CF_TUNNEL_TOKEN` | Cloudflare Tunnel 连接令牌 |

仅在服务器本地运行 Web 服务时，不需要真实 Cloudflare Token，也不需要配置公网域名。

完成配置后执行：

```bash
chmod 600 .env
docker compose config --quiet
```

第一条命令限制配置文件的访问权限；第二条命令检查 Compose 配置能否正常解析。

**注意：** `.env` 可能包含访问令牌，不得上传至公开仓库。项目的 `.gitignore` 已将该文件排除。

## 5. Docker 部署与启动

### 5.1 构建并启动 Web 服务

首次部署建议先单独运行 Web 服务，确认项目可以在服务器本地正常访问，再配置外部访问。

在项目根目录执行：

```bash
docker compose up -d --build web
```

Docker 将根据 `Dockerfile`：

1. 使用 `python:3.11-slim` 构建基础环境。
2. 安装 `web_backend/requirements.txt` 中的依赖。
3. 复制前后端代码到 `/app`。
4. 创建非 root 运行用户。
5. 启动 Uvicorn，加载 FastAPI 应用。

容器内服务监听 `0.0.0.0:8000`，通过 Compose 映射至宿主机：

```text
127.0.0.1:18083 → web:8000
```

这里的 `18083` 是默认宿主机端口，实际端口由 `LOCAL_PORT` 决定。

### 5.2 检查运行状态

执行：

```bash
docker compose ps
```

查看 Web 容器的运行情况。

随后检查健康接口：

```bash
curl -i http://127.0.0.1:18083/api/health
```

正常情况下，应收到 HTTP 200 及包含 `status` 和 `source_url` 的 JSON 响应。

其中：

- `status` 表示 API 服务状态。
- `source_url` 表示当前程序使用的固定招聘数据源。

健康接口返回成功只能说明 Web 服务能够响应请求，不能证明外部招聘网页一定能够访问或采集成功。

### 5.3 打开网页

在服务器本机浏览器访问：

http://127.0.0.1:18083/

如果服务器没有图形界面，也可以从其他电脑建立 SSH 端口转发：

```bash
ssh -L 18083:127.0.0.1:18083 用户名@服务器地址
```

保持 SSH 连接，在该电脑浏览器打开：

http://127.0.0.1:18083/

这种方法不需要将 Web 服务端口直接暴露到公网。

## 6. Cloudflare Tunnel 配置

项目的 `compose.yaml` 已包含独立的 `tunnel` 服务，可通过 Cloudflare Tunnel 将内部 Web 服务连接至 Cloudflare 网络。

该功能是可选部署方案，不影响本地 Docker 服务的运行。

### 6.1 创建 Tunnel

在 Cloudflare Zero Trust 控制台创建一个新的 Cloudflare Tunnel，选择 Cloudflared 连接方式，并获取连接令牌。

将令牌填写到 Ubuntu 项目目录下的 `.env`：

```dotenv
CF_TUNNEL_TOKEN=实际获取的令牌
```

不要将令牌写进源码文件，也不要提交至 GitHub。

### 6.2 配置访问路由

在 Cloudflare Tunnel 中添加公开应用访问路由。

配置示例：

| 项目 | 配置 |
|---|---|
| 公网域名 | `jobs.example.com` |
| 服务协议 | HTTP |
| 内部目标 | `http://web:8000` |

`web` 是 Docker Compose 内部的服务名称。

由于 Cloudflared 与 Web 服务运行在不同容器中，不能将隧道的内部目标写成 `http://localhost:18083`。

### 6.3 启动 Tunnel

完成令牌及路由配置后，执行：

```bash
docker compose up -d tunnel
```

检查运行情况：

```bash
docker compose ps
docker compose logs --tail 100 tunnel
```

### 6.4 公网访问限制

**当前仓库版本尚不能仅通过填写 `PUBLIC_HOSTNAME` 完成公网域名访问。**

在 `web_backend/app.py` 中，`TrustedHostMiddleware` 当前只允许：

- `localhost`
- `127.0.0.1`
- `testserver`

因此，Cloudflare 使用实际公网域名转发请求时，应用可能返回 HTTP 400。

虽然 `.env.example` 提供了 `PUBLIC_HOSTNAME` 参数，但现有应用代码没有自动将它加入允许的主机列表。

在完成相应应用配置与测试前，不应将公网访问描述为已验证可用。

此外，Web 应用自身没有用户登录认证。如果将其发布至公网，应先配置 Cloudflare Access 等访问控制，限制允许访问的用户。

本地 Docker 部署不受上述公网域名限制影响。

## 7. 数据存储与输出

### 7.1 数据保存方式

系统不依赖数据库，任务记录与采集结果直接保存在文件系统中。

容器内数据目录为：

```text
/app/web_backend/data/
```

`compose.yaml` 将该目录映射到 Docker 命名数据卷 `recruitment_data`。

因此，常规停止、启动或重新构建 Web 容器不会直接删除已经保存的任务数据。

### 7.2 输出文件结构

每个采集任务使用独立任务 ID 建立目录。

```text
web_backend/data/
└── <task-id>/
    ├── task.json
    ├── results.json
    └── results.csv
```

文件说明：

| 文件 | 内容 |
|---|---|
| `task.json` | 任务状态、进度、统计及错误记录 |
| `results.json` | JSON 格式的岗位采集结果 |
| `results.csv` | 可下载的 CSV 格式岗位结果 |

CSV 文件使用 UTF-8-SIG 编码，主要字段包括岗位名称、学历、专业及详情链接。

采集失败或尚未完成的任务可能只有 `task.json`，不一定生成结果文件。

### 7.3 数据持久化说明

执行以下命令通常不会删除命名数据卷：

```bash
docker compose down
```

但以下命令会同时删除 Compose 管理的数据卷，可能导致历史采集记录丢失：

```bash
docker compose down -v
```

**除非确认不再需要历史数据，否则不要使用 `down -v`。**

## 8. 日志、更新与备份

### 8.1 查看日志

查看 Web 服务日志：

```bash
docker compose logs --tail 100 web
```

持续查看：

```bash
docker compose logs -f web
```

查看 Tunnel 日志：

```bash
docker compose logs --tail 100 tunnel
```

### 8.2 更新项目

当 GitHub 仓库有新提交时，在项目根目录执行：

```bash
git pull --ff-only
docker compose up -d --build web
```

以上操作会拉取最新代码，并重新构建和启动 Web 容器。

更新前应确认没有正在执行的采集任务。容器重启可能中断尚未完成的任务。

若更新涉及 Compose 配置或 Cloudflare Tunnel，还需要按实际修改情况重新创建相关服务。

### 8.3 备份采集数据

建议在没有采集任务运行时进行备份。

首先创建备份目录并停止 Web 服务：

```bash
mkdir -p backups
docker compose stop web
```

随后执行：

```bash
docker compose run --rm --no-deps \
  --user 0:0 \
  -v "$PWD/backups:/backup" \
  --entrypoint sh web \
  -c 'cp -a /app/web_backend/data/. /backup/'
```

备份文件将保存到项目根目录下的 `backups/`。

最后重新启动 Web 服务：

```bash
docker compose start web
```

备份目录仅用于保存运行数据，不应直接作为源码文件提交至公开仓库。备份文件也应避免包含不必要的个人信息。

## 9. 常见问题

### 9.1 Docker 容器无法启动

首先查看：

```bash
docker compose ps -a
docker compose logs --tail 100 web
```

检查 Docker 服务、镜像构建日志、依赖安装及配置文件是否存在错误。

### 9.2 本地端口被占用

如果默认端口 `18083` 已经被其他程序使用，可修改 `.env`：

```dotenv
LOCAL_PORT=18084
```

然后重新创建 Web 容器：

```bash
docker compose up -d --force-recreate web
```

新的本地访问地址为：

http://127.0.0.1:18084/

### 9.3 API 返回 HTTP 400

如果本地 `127.0.0.1` 可以访问，但通过公网域名返回 HTTP 400，应重点检查 `TrustedHostMiddleware`。

当前版本未自动支持 `PUBLIC_HOSTNAME` 中配置的主机名。

仅重启容器或修改 `.env` 不一定能解决这一问题。

### 9.4 创建采集任务返回 HTTP 403

系统对 POST 请求进行了同源检查。

如果请求的 Origin、Host 或访问协议不一致，可能被拒绝。

应检查浏览器实际访问地址、反向代理传递的请求信息及应用同源校验设置。

不建议通过直接关闭同源检查来解决。

### 9.5 招聘数据采集失败

系统固定使用浙江大学医学院附属第二医院招聘网页的 Wayback Machine 历史存档：

https://web.archive.org/web/20260515165600/https://zp.z2hospital.com/department/detailInfomore.action

如果历史存档不可用、网页结构变化或发生连接超时、SSL 错误等情况，采集任务可能失败。

这类问题不一定意味着 Docker 或 FastAPI 部署失败。

应分别检查：

1. `/api/health` 是否能够正常返回。
2. Docker 服务是否运行正常。
3. 固定历史网页存档是否能够安全访问。
4. 采集任务的错误信息及日志。

不得为了使结果显示成功而使用虚构岗位信息替代真实采集结果。

## 10. 运行与使用注意事项

1. 本项目主要用于 Python 课程学习与教学演示。
2. 数据来源为历史招聘网页存档，不代表医院当前招聘计划。
3. 系统使用固定采集地址，不提供任意网址输入功能。
4. 实际采集依赖外部网络及存档网站的可用性。
5. 当前生产服务采用单个 Uvicorn Worker，不应同时运行多个实例共用同一数据目录。
6. Web API 本身没有用户身份认证，公网部署前必须实施适当的访问控制。
7. `.env`、Cloudflare Token 及实际运行数据不应随意提交至公开仓库。
8. 本文档根据当前仓库的源码和部署配置编写；其中公网访问限制属于已知问题，不能视为已完成的公网部署验证。

## 11. 部署总结

本项目采用 FastAPI 与 Docker Compose 实现前后端统一部署，使用 JSON、CSV 文件保存任务状态及采集结果，通过 Docker 命名数据卷实现持久化存储。

在 Ubuntu 24.04 环境下，按照本文档可完成 Docker Web 服务的构建、配置和本地访问检查。

Cloudflare Tunnel 作为可选的远程访问方式，相关容器与路由配置已经提供，但当前版本仍需要处理公网域名的主机校验问题并完成实际验证。

本项目的运行和采集结果应以真实环境中的测试情况为准，不将历史存档采集成功率或外部网络可用性作为部署成功的必要条件。