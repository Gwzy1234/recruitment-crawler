"""Deliberate external-network substitution for local fixture tests only."""
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import requests

from web_backend.collector import Crawler, LIST_URL

FIXTURES = Path(__file__).parent / "fixtures"


def response(url, html="", status=200, headers=None):
    result = requests.Response()
    result.url = url
    result.status_code = status
    result._content = html.encode("utf-8")
    result._content_consumed = True
    result.headers.update({"Content-Type": "text/html; charset=utf-8", **(headers or {})})
    return result


class FixtureSession:
    def __init__(self, gate=None, list_status=200, delay=0, error_ids=None, list_html=None):
        self.headers = {}
        self.calls = []
        self.gate = gate
        self.list_status = list_status
        self.delay = delay
        self.error_ids = error_ids or {}
        self.list_html = list_html

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if url == LIST_URL and self.gate:
            if not self.gate.wait(5):
                raise requests.Timeout("Test gate was not released")
        if self.delay:
            threading.Event().wait(self.delay)
        if url == LIST_URL:
            html = self.list_html if self.list_html is not None else (FIXTURES / "list.html").read_text()
            return response(url, html, self.list_status)
        job_id = parse_qs(urlsplit(url).query)["uuid"][0]
        if job_id in self.error_ids:
            raise self.error_ids[job_id]
        if job_id == "not-found":
            return response(url, "存档不存在", 404)
        if job_id == "missing":
            return response(url, (FIXTURES / "partial.html").read_text())
        if job_id == "internal":
            return response(url, '<div class="tr_name">学历学位</div><div>硕士及以上</div><div class="tr_name">专业</div><div>内科学,临床医学</div>')
        if job_id == "nursing":
            return response(url, '<div class="tr_name">学历学位</div><div>本科及以上</div><div class="tr_name">专业</div><div>护理学</div>')
        return response(url, (FIXTURES / "detail.html").read_text())


class FixtureCrawler(Crawler):
    source_kind = "local_html_test"

    def __init__(self, session=None, interval=0):
        self.fixture_session = session or FixtureSession()
        super().__init__(session_factory=lambda: self.fixture_session, interval=interval, retries=0)
