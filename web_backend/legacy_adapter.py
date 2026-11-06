"""实际调用根目录 team-task.py 原始函数的 FastAPI 采集适配层。

核心抓取、岗位列表解析、岗位详情解析均由原版 team-task.py 负责。
本模块只管理任务事件、逐条异常、取消与供前端使用的数据形状。
"""
import importlib.util
import threading
from pathlib import Path
from urllib.parse import urlsplit

from .collector import CollectionError, CollectionStopped, describe_error

LEGACY_FILE = Path(__file__).resolve().parent.parent / "team-task.py"
_spec = importlib.util.spec_from_file_location("recruitment_original_team_task", LEGACY_FILE)
if _spec is None or _spec.loader is None:
    raise ImportError(f"无法加载原始爬虫文件: {LEGACY_FILE}")
legacy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(legacy)

LIST_URL = "https://web.archive.org/web/20260515165600/https://zp.z2hospital.com/department/detailInfomore.action"


def _legacy_url_is_fixed_wayback(url):
    # 原脚本固定拼接历史存档链接；仅接受它生成的同源路径。
    parts = urlsplit(url)
    return (parts.scheme == "https" and parts.hostname == "web.archive.org"
            and parts.path.startswith("/web/20260515165600/https://zp.z2hospital.com/department/detailInfo.action")
            and parts.username is None and parts.password is None and parts.port in (None, 443))


class LegacyCrawler:
    """保留旧爬虫 1 秒间隔；直接执行 get_page / parse_job_list / parse_job_detail。"""
    source_kind = "wayback_team_task"

    def __init__(self, interval=1.0):
        self.interval = interval

    def run(self, emit, stop=None):
        stop = stop or threading.Event()
        if stop.is_set():
            raise CollectionStopped("任务已停止。")
        emit("list_started", {"message": "正在调用原始 team-task.py 获取招聘列表。"})
        try:
            raw = legacy.parse_job_list(legacy.get_page(LIST_URL), LIST_URL)
        except Exception as exc:
            raise CollectionError("原始爬虫无法获取或解析岗位列表：" + describe_error(exc)) from exc
        if not raw:
            raise CollectionError("原始 team-task.py 未解析出任何岗位；可能是存档页面不可访问或结构变化。")
        emit("list_parsed", {"discovered": len(raw), "message": f"原始 team-task.py 已解析出 {len(raw)} 个岗位。"})
        jobs = []
        for idx, item in enumerate(raw, 1):
            if stop.is_set():
                raise CollectionStopped("服务停止，采集任务已中断。")
            title = str(item.get("title") or "").strip()
            url = str(item.get("detail_url") or "").strip()
            result = {"id": idx, "title": title, "education": "", "major": "",
                      "link": url, "parse_status": "pending", "error": ""}
            jobs.append(result)
            emit("detail_started", {"current_job": title or "未获取岗位名称", "message": "原始爬虫正在处理岗位详情。"})
            try:
                if not _legacy_url_is_fixed_wayback(url):
                    raise CollectionError("原始爬虫产生的岗位链接不在固定存档范围内。")
                if stop.wait(self.interval):
                    raise CollectionStopped("服务停止，采集任务已中断。")
                detail = legacy.parse_job_detail(legacy.get_page(url))
                result["education"] = str(detail.get("education") or "").strip()
                result["major"] = str(detail.get("major") or "").strip()
                result["parse_status"] = "parsed"
            except CollectionStopped:
                raise
            except Exception as exc:
                # 保持原始脚本对单个详情出错时跳过、继续其他岗位的行为。
                result["parse_status"] = "failed"
                result["error"] = describe_error(exc)
            emit("detail_finished", {"job": dict(result), "message": "岗位解析成功。" if result["parse_status"] == "parsed" else result["error"]})
        return jobs
