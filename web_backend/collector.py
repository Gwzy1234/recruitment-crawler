"""Fixed-source requests/BeautifulSoup adapter; no import of legacy crawler code."""
import re
import threading
from urllib.parse import urlencode, urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

LIST_URL = (
    "https://web.archive.org/web/20260515165600/"
    "https://zp.z2hospital.com/department/detailInfomore.action"
)
DETAIL_PREFIX = LIST_URL.rsplit("/", 1)[0] + "/detailInfo.action?"
ARCHIVE_PATH = re.compile(
    r"^/web/\d+(?:[a-z_]+)?/https?://zp\.z2hospital\.com/department/"
    r"(?:detailInfomore|detailInfo)\.action$"
)


class CollectionError(Exception):
    """Expected request, archive or page-structure failure."""


class CollectionStopped(CollectionError):
    pass


def clean(value):
    value = str(value or "").strip()
    return "" if value.lower() == "none" else value


def parse_job_list(html):
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("li.zp_li")
    if not cards:
        raise CollectionError("列表未找到 li.zp_li 岗位，可能无存档、返回错误页或页面结构已变化。")
    jobs = []
    for index, card in enumerate(cards, 1):
        title_node = card.find("div", class_="left_name")
        title = clean(title_node.get_text(strip=True)) if title_node else ""
        match = re.search(r"(['\"])([^'\"]+)\1", card.get("onclick", ""))
        job_id = match.group(2).strip() if match else ""
        valid_id = re.fullmatch(r"[A-Za-z0-9_-]{1,128}", job_id)
        link = DETAIL_PREFIX + urlencode({"uuid": job_id, "zplx": "507"}) if valid_id else ""
        errors = []
        if not title:
            errors.append("缺少岗位名称")
        if not link:
            errors.append("无法从 onclick 提取岗位 UUID")
        jobs.append({"id": index, "title": title, "education": "", "major": "", "link": link,
                     "parse_status": "pending", "error": "；".join(errors)})
    return jobs


def parse_job_detail(html):
    soup = BeautifulSoup(html, "html.parser")
    data = {"education": "", "major": ""}
    recognized = 0
    for field in soup.find_all("div", class_="tr_name"):
        name = re.sub(r"\s+", "", field.get_text()).rstrip(":：")
        key = {"学历学位": "education", "专业": "major"}.get(name)
        if not key:
            continue
        recognized += 1
        sibling = field.find_next_sibling("div")
        if sibling is not None and "tr_name" not in sibling.get("class", []):
            data[key] = clean(sibling.get_text(strip=True))
    if not recognized:
        raise CollectionError("详情未找到学历学位或专业字段，可能无存档或页面结构已变化。")
    return data


def allowed_url(url):
    try:
        parts = urlsplit(url)
        return (parts.scheme == "https" and parts.hostname == "web.archive.org"
                and parts.port in (None, 443) and not parts.username and not parts.password
                and bool(ARCHIVE_PATH.fullmatch(parts.path)))
    except ValueError:
        return False


def describe_error(error):
    if isinstance(error, requests.exceptions.SSLError):
        return "SSL 连接失败，无法安全访问网页存档。"
    if isinstance(error, requests.exceptions.Timeout):
        return "网页存档请求超时。"
    if isinstance(error, requests.exceptions.HTTPError):
        code = error.response.status_code if error.response is not None else "未知"
        return f"HTTP {code}：" + ("网页存档不存在或不可访问。" if code == 404 else "网页存档请求失败。")
    if isinstance(error, requests.exceptions.RequestException):
        return "网络连接失败，无法访问网页存档。"
    return str(error)


class Crawler:
    source_kind = "wayback"

    def __init__(self, session_factory=requests.Session, interval=1.0, retries=1, timeout=(5, 15)):
        self.session_factory = session_factory
        self.interval = interval
        self.retries = retries
        self.timeout = timeout

    def get_page(self, session, url, emit, stop):
        if not allowed_url(url):
            raise CollectionError("拒绝访问固定招聘存档以外的地址。")
        for attempt in range(self.retries + 1):
            if stop.is_set():
                raise CollectionStopped("服务停止，采集任务已中断。")
            emit("request", {"message": f"正在请求网页存档（第 {attempt + 1} 次尝试）"})
            try:
                current_url = url
                for redirect in range(6):
                    response = session.get(current_url, timeout=self.timeout, allow_redirects=False)
                    try:
                        if response.status_code in (301, 302, 303, 307, 308):
                            target = urljoin(current_url, response.headers.get("Location", ""))
                            if redirect == 5 or not allowed_url(target):
                                raise CollectionError("存档重定向至不允许的地址或重定向次数过多。")
                            current_url = target
                            continue
                        response.raise_for_status()
                        response.encoding = response.apparent_encoding or "utf-8"
                        return response.text
                    finally:
                        response.close()
            except (requests.exceptions.RequestException, CollectionError) as error:
                retryable = isinstance(error, (requests.exceptions.Timeout, requests.exceptions.ConnectionError))
                if isinstance(error, requests.exceptions.SSLError):
                    retryable = False
                if isinstance(error, requests.exceptions.HTTPError) and error.response is not None:
                    retryable = error.response.status_code in (429, 500, 502, 503, 504)
                if not retryable or attempt == self.retries:
                    raise CollectionError(describe_error(error)) from error
                emit("retry", {"message": describe_error(error) + " 正在等待有限重试。"})
                if stop.wait(1 + attempt):
                    raise CollectionStopped("服务停止，采集任务已中断。")
        raise CollectionError("网页存档请求失败。")

    def run(self, emit, stop=None):
        stop = stop or threading.Event()
        emit("list_started", {"message": "正在读取固定招聘列表存档，岗位总数暂未知。"})
        with self.session_factory() as session:
            session.headers.update({"User-Agent": "HospitalRecruitmentArchive/1.0 (local educational project)"})
            jobs = parse_job_list(self.get_page(session, LIST_URL, emit, stop))
            emit("list_parsed", {"discovered": len(jobs), "message": f"发现 {len(jobs)} 个岗位，开始逐个读取详情。"})
            for job in jobs:
                if stop.is_set():
                    raise CollectionStopped("服务停止，采集任务已中断。")
                emit("detail_started", {"current_job": job["title"] or "未获取岗位名称", "message": "正在处理岗位详情。"})
                try:
                    if job["error"]:
                        raise CollectionError(job["error"])
                    if stop.wait(self.interval):
                        raise CollectionStopped("服务停止，采集任务已中断。")
                    job.update(parse_job_detail(self.get_page(session, job["link"], emit, stop)))
                    job["parse_status"] = "parsed"
                except CollectionStopped:
                    raise
                except Exception as error:
                    # Every failed card is retained; one bad detail never stops the list.
                    job["parse_status"] = "failed"
                    job["error"] = describe_error(error)
                emit("detail_finished", {"job": dict(job), "message": "岗位解析成功。" if job["parse_status"] == "parsed" else job["error"]})
            return jobs
