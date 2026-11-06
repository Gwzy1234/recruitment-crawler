"""Single local worker, durable task metadata and per-task UTF-8-SIG CSV files."""
import copy
import csv
import errno
import json
import logging
import os
import re
import tempfile
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from .collector import CollectionStopped, describe_error
from .legacy_adapter import LegacyCrawler as Crawler, LIST_URL

ACTIVE_STATES = {"queued", "fetching_list", "fetching_details", "saving"}
FINAL_STATES = {"completed", "partial", "failed", "interrupted"}
TASK_ID = re.compile(r"^[a-f0-9]{32}$")
logger = logging.getLogger(__name__)


def now():
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path, value):
    fd, temp = tempfile.mkstemp(prefix=".metadata-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(value, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp, path)
    finally:
        Path(temp).unlink(missing_ok=True)


class TaskBusy(Exception):
    def __init__(self, task=None):
        self.task = task


class TaskManager:
    def __init__(self, data_dir, crawler_factory=Crawler):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.crawler_factory = crawler_factory
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="recruitment")
        self.records = {}
        self.active_id = None
        self._load()

    def _process_lock(self):
        handle = (self.data_dir / ".collector.lock").open("a+")
        try:
            if os.name == "nt":
                import msvcrt
                handle.seek(0, os.SEEK_END)
                if handle.tell() == 0:
                    handle.write("\0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            handle.close()
            if isinstance(error, BlockingIOError) or error.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                raise TaskBusy() from None
            raise
        return handle

    def _load(self):
        try:
            handle = self._process_lock()
        except TaskBusy:
            handle = None
        try:
            for path in self.data_dir.glob("*/task.json"):
                if not TASK_ID.fullmatch(path.parent.name):
                    continue
                try:
                    record = json.loads(path.read_text(encoding="utf-8"))
                    if record["id"] != path.parent.name or record["status"] not in ACTIVE_STATES | FINAL_STATES:
                        continue
                    if record["status"] in ACTIVE_STATES and handle is not None:
                        record.update(status="interrupted", finished_at=now(), error="服务上次退出时任务尚未完成，未生成可下载结果。", result_ready=False)
                        atomic_json(path, record)
                    self.records[record["id"]] = record
                except (OSError, ValueError, KeyError):
                    logger.warning("Skipping unreadable task metadata: %s", path)
        finally:
            if handle:
                handle.close()

    def _persist(self, record):
        atomic_json(self.data_dir / record["id"] / "task.json", record)

    def _public(self, record):
        value = copy.deepcopy(record)
        ready = (record.get("result_ready", False) and record["status"] in {"completed", "partial"}
                 and (self.data_dir / record["id"] / "results.csv").is_file()
                 and (self.data_dir / record["id"] / "results.json").is_file())
        value["result_ready"] = ready
        value["download_url"] = f"/api/tasks/{record['id']}/download" if ready else None
        return value

    def get(self, task_id):
        with self.lock:
            return self._public(self.records[task_id])

    def overview(self, limit=20):
        with self.lock:
            records = sorted(self.records.values(), key=lambda item: item["created_at"], reverse=True)
            public = [self._public(item) for item in records]
            active = next((item for item in public if item["status"] in ACTIVE_STATES), None)
            results = [item for item in public if item["result_ready"]]
            latest_result = max(results, key=lambda item: item["finished_at"]) if results else None
            return {"active_task": active, "latest_task": public[0] if public else None,
                    "latest_result": latest_result, "tasks": public[:limit]}

    def start(self):
        with self.lock:
            if self.stop.is_set():
                raise RuntimeError("服务正在停止。")
            if self.active_id is not None:
                raise TaskBusy(self._public(self.records[self.active_id]))
            handle = self._process_lock()
            record = None
            try:
                crawler = self.crawler_factory()
                task_id = uuid.uuid4().hex
                (self.data_dir / task_id).mkdir(exist_ok=False)
                record = {"id": task_id, "status": "queued", "source_url": LIST_URL,
                          "source_kind": crawler.source_kind, "created_at": now(), "started_at": None,
                          "finished_at": None, "discovered": None, "processed": 0, "parsed": 0,
                          "failed": 0, "complete": 0, "incomplete": 0, "progress": None,
                          "current_job": "", "message": "任务已创建，等待请求固定招聘列表。", "error": None,
                          "events": [], "result_ready": False}
                self.records[task_id] = record
                self._persist(record)
                self.active_id = task_id
                self.executor.submit(self._run, task_id, crawler, handle)
                return self._public(record)
            except Exception:
                if record is not None:
                    record.update(status="failed", finished_at=now(), result_ready=False,
                                  error="任务初始化失败，请检查数据目录权限与服务状态。")
                    try:
                        self._persist(record)
                    except OSError:
                        logger.exception("Cannot persist task initialization failure")
                handle.close()
                self.active_id = None
                raise

    def _event(self, task_id, event, payload):
        with self.lock:
            record = self.records[task_id]
            if event == "list_started":
                record.update(status="fetching_list", started_at=now())
            elif event == "list_parsed":
                record.update(status="fetching_details", discovered=payload["discovered"], progress=0)
            elif event == "detail_finished":
                job = payload["job"]
                record["processed"] += 1
                if job["parse_status"] == "parsed":
                    record["parsed"] += 1
                    if all(job[key] for key in ("title", "education", "major", "link")):
                        record["complete"] += 1
                    else:
                        record["incomplete"] += 1
                else:
                    record["failed"] += 1
                record["progress"] = record["processed"] * 100 // record["discovered"]
            if "current_job" in payload:
                record["current_job"] = payload["current_job"]
            record["message"] = payload["message"]
            record["events"].append({"time": now(), "type": event, "message": payload["message"],
                                     "job": record["current_job"]})
            record["events"] = record["events"][-100:]
            self._persist(record)

    def _save_results(self, record, jobs):
        directory = self.data_dir / record["id"]
        # Exclusive creation in a unique task directory. No legacy CSV path is used.
        with (directory / "results.csv.part").open("x", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file)
            writer.writerow(["岗位名", "学历", "专业", "链接"])
            for job in jobs:
                cells = []
                for key in ("title", "education", "major", "link"):
                    text = job[key] or "none"
                    if re.match(r"^[\s\ufeff]*[=+@-]", text):
                        text = "'" + text
                    cells.append(text)
                writer.writerow(cells)
            file.flush()
            os.fsync(file.fileno())
        payload = {"task_id": record["id"], "source_url": LIST_URL, "source_kind": record["source_kind"], "jobs": jobs}
        with (directory / "results.json.part").open("x", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        (directory / "results.csv.part").rename(directory / "results.csv")
        (directory / "results.json.part").rename(directory / "results.json")

    def _run(self, task_id, crawler, handle):
        record = self.records[task_id]
        try:
            jobs = crawler.run(lambda event, payload: self._event(task_id, event, payload), self.stop)
            with self.lock:
                record.update(status="saving", current_job="", message="详情处理结束，正在保存本次结果。")
                self._persist(record)
            self._save_results(record, jobs)
            with self.lock:
                status = "partial" if record["failed"] or record["incomplete"] else "completed"
                record.update(status=status, result_ready=True, finished_at=now(),
                              message="采集结束，部分岗位失败或字段不完整。" if status == "partial" else "采集完成，结果已保存。")
                self._persist(record)
        except Exception as error:
            logger.warning("Task %s ended: %s", task_id, error)
            with self.lock:
                record.update(status="interrupted" if isinstance(error, CollectionStopped) else "failed",
                              finished_at=now(), current_job="", result_ready=False,
                              error=describe_error(error) if not isinstance(error, OSError) else "结果写入失败，请检查磁盘空间和数据目录权限。",
                              message="本次任务未生成可下载结果；已有历史结果保留。")
                try:
                    self._persist(record)
                except OSError:
                    logger.exception("Cannot persist task failure")
        finally:
            with self.lock:
                self.active_id = None
                handle.close()

    def result(self, task_id):
        record = self.get(task_id)
        if not record["result_ready"]:
            raise ValueError("本次任务尚未生成结果。")
        return json.loads((self.data_dir / task_id / "results.json").read_text(encoding="utf-8"))

    def close(self):
        self.stop.set()
        self.executor.shutdown(wait=True, cancel_futures=False)
