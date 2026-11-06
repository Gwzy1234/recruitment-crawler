"""Run from project root: python -m uvicorn web_backend.app:app --host 127.0.0.1 --port 8767"""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .collector import Crawler, LIST_URL
from .tasks import TASK_ID, TaskBusy, TaskManager

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = Path(__file__).resolve().parent / "data"


class StartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


def create_app(data_dir=DEFAULT_DATA_DIR, crawler_factory=Crawler):
    @asynccontextmanager
    async def lifespan(application):
        manager = TaskManager(data_dir, crawler_factory)
        application.state.manager = manager
        try:
            yield
        finally:
            await asyncio.to_thread(manager.close)

    application = FastAPI(title="医院招聘历史存档采集服务", lifespan=lifespan)
    application.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "testserver"])

    @application.middleware("http")
    async def local_origin(request: Request, call_next):
        if request.method == "POST":
            origin = request.headers.get("origin")
            if origin and (urlsplit(origin).netloc != request.url.netloc or urlsplit(origin).scheme != request.url.scheme):
                return JSONResponse({"detail": "只允许同源页面启动任务。"}, status_code=403)
            if request.headers.get("content-type", "").split(";", 1)[0] != "application/json":
                return JSONResponse({"detail": "请使用 application/json。"}, status_code=415)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    def manager():
        return application.state.manager

    def get_task(task_id):
        if not TASK_ID.fullmatch(task_id):
            raise HTTPException(404, "任务不存在。")
        try:
            return manager().get(task_id)
        except KeyError:
            raise HTTPException(404, "任务不存在。") from None

    @application.get("/api/health")
    def health():
        return {"status": "ok", "source_url": LIST_URL}

    @application.get("/api/tasks")
    def tasks(limit: int = Query(20, ge=1, le=100)):
        return manager().overview(limit)

    @application.post("/api/tasks", status_code=202)
    def start_task(payload: StartRequest):
        try:
            return manager().start()
        except TaskBusy as error:
            raise HTTPException(409, {"message": "已有采集任务正在运行，请勿重复启动。", "task": error.task}) from None
        except (OSError, RuntimeError):
            raise HTTPException(503, "任务无法启动，请检查服务状态和数据目录权限。") from None

    @application.get("/api/tasks/{task_id}")
    def task_status(task_id: str):
        return get_task(task_id)

    @application.get("/api/tasks/{task_id}/results")
    def results(task_id: str):
        task = get_task(task_id)
        if not task["result_ready"]:
            raise HTTPException(409, "本次任务尚未生成可用结果。")
        return {**manager().result(task_id), "task": task}

    @application.get("/api/results/latest")
    def latest_results():
        task = manager().overview()["latest_result"]
        if task is None:
            raise HTTPException(404, "尚无已保存的结果。")
        return {**manager().result(task["id"]), "task": task}

    @application.get("/api/tasks/{task_id}/download")
    def download(task_id: str):
        task = get_task(task_id)
        if not task["result_ready"]:
            raise HTTPException(409, "CSV 尚未生成，本次任务暂不可下载。")
        return FileResponse(manager().data_dir / task_id / "results.csv", media_type="text/csv; charset=utf-8",
                            filename=f"招聘数据_{task_id}.csv")

    # Explicit file allowlist: never expose the project root, test fixtures or stored data.
    @application.get("/")
    def index():
        return FileResponse(ROOT / "frontend" / "index.html", media_type="text/html")

    @application.get("/{asset}")
    def asset(asset: str):
        media = {"styles.css": "text/css", "app.js": "text/javascript", "data.js": "text/javascript"}
        if asset not in media:
            raise HTTPException(404, "文件不存在。")
        return FileResponse(ROOT / "frontend" / asset, media_type=media[asset])

    return application


app = create_app()
