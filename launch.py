"""爬虫项目双平台入口；准备运行环境并打开网页，不自动发起采集。"""

import argparse
import hashlib
import importlib.metadata
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import urllib.request
import venv
import webbrowser

ROOT = Path(__file__).resolve().parent
RUNTIME = ROOT / ".runtime"


def prepare():
    if Path(sys.prefix).resolve() != RUNTIME.resolve():
        executable = RUNTIME / ("Scripts/python.exe" if os.name == "nt" else "bin/python3")
        if not executable.is_file():
            if RUNTIME.exists():
                raise RuntimeError(".runtime 不完整或来自另一台电脑，请将它移走后重新启动；不要删除原始代码和数据")
            print("首次启动：正在创建独立 Python 环境……", flush=True)
            venv.EnvBuilder(with_pip=True).create(RUNTIME)
        return subprocess.call([str(executable), "-B", str(ROOT / "launch.py"), *sys.argv[1:]], cwd=ROOT)

    requirements = ROOT / "web_backend" / "requirements.txt"
    digest = hashlib.sha256(requirements.read_bytes()).hexdigest()
    marker = RUNTIME / ".requirements.sha256"
    ready = marker.is_file() and marker.read_text(encoding="ascii").strip() == digest
    try:
        for line in requirements.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.lstrip().startswith("#"):
                package, version = line.strip().split("==", 1)
                ready = ready and importlib.metadata.version(package) == version
    except (importlib.metadata.PackageNotFoundError, ValueError):
        ready = False
    if not ready:
        print("首次启动需要联网安装依赖，请等待……", flush=True)
        subprocess.run([sys.executable, "-m", "pip", "--disable-pip-version-check", "install", "-r", str(requirements)], check=True)
        marker.write_text(digest + "\n", encoding="ascii")
    return None


def open_page(server, url, stopped):
    deadline = time.monotonic() + 45
    while not stopped.is_set() and time.monotonic() < deadline:
        if server.started:
            try:
                with urllib.request.urlopen(url + "api/health", timeout=1) as response:
                    if response.status == 200:
                        if not webbrowser.open(url):
                            print("请手动打开：" + url, flush=True)
                        return
            except (OSError, webbrowser.Error):
                pass
        stopped.wait(0.2)


def main():
    parser = argparse.ArgumentParser(description="医院招聘爬虫一键启动")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8767")))
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("端口必须在 1～65535 之间")
    try:
        if sys.version_info < (3, 11):
            raise RuntimeError("请安装 Python 3.11 或更高版本")
        os.chdir(ROOT)
        os.environ["PYTHONUTF8"] = "1"
        os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        print("医院招聘历史存档爬虫 · 一键启动", flush=True)
        result = prepare()
        if result is not None:
            return result

        import uvicorn
        url = f"http://127.0.0.1:{args.port}/"
        server = uvicorn.Server(uvicorn.Config("web_backend.app:app", host="127.0.0.1", port=args.port, workers=1))
        stopped = threading.Event()
        try:
            if not args.no_browser:
                threading.Thread(target=open_page, args=(server, url, stopped), daemon=True).start()
            print("网页地址：" + url + "\n请保留本窗口，按 Ctrl+C 停止服务。", flush=True)
            server.run()
            return 0 if server.started else 1
        finally:
            stopped.set()
    except KeyboardInterrupt:
        print("\n已停止。", flush=True)
        return 0
    except Exception as error:
        print("启动失败：" + str(error) + "\n请检查 Python、网络或端口是否被占用。", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
