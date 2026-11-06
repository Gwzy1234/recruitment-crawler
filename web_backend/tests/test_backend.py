import csv
import io
import json
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock, patch

import requests
from fastapi.testclient import TestClient

from web_backend.app import create_app
from web_backend.collector import (CollectionError, CollectionStopped, Crawler, LIST_URL,
                                   allowed_url, parse_job_detail, parse_job_list)
from web_backend.tasks import TaskBusy, TaskManager
from web_backend.tests.support import FIXTURES, FixtureCrawler, FixtureSession, response


def finished(client, task_id):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        task = client.get(f"/api/tasks/{task_id}").json()
        if task["status"] not in {"queued", "fetching_list", "fetching_details", "saving"}:
            return task
        threading.Event().wait(.01)
    raise AssertionError("Fixture task did not finish")


class ParserTests(unittest.TestCase):
    def test_fixed_source_and_single_double_quote_uuid(self):
        jobs = parse_job_list((FIXTURES / "list.html").read_text())
        self.assertEqual(len(jobs), 12)
        self.assertIn("uuid=imaging&zplx=507", jobs[0]["link"])
        self.assertIn("uuid=internal&zplx=507", jobs[1]["link"])
        self.assertIn("UUID", jobs[5]["error"])
        self.assertIn("<img", jobs[6]["title"])
        self.assertTrue(all(allowed_url(job["link"]) for job in jobs if job["link"]))

    def test_empty_or_error_list_is_not_reported_as_success(self):
        for html in ["", "<h1>No archived snapshots</h1>", "<ul></ul>"]:
            with self.assertRaises(CollectionError):
                parse_job_list(html)

    def test_missing_title_and_unsafe_onclick_are_retained_failures(self):
        job = parse_job_list('<li class="zp_li" onclick="evil(\'http://evil.test\')"></li>')[0]
        self.assertFalse(job["link"])
        self.assertIn("名称", job["error"])
        job = parse_job_list('<li class="zp_li" onclick="open(\'http://evil.test\',\'safe\')"><div class="left_name">医生</div></li>')[0]
        self.assertFalse(job["link"])

    def test_detail_extracts_unicode_comma_and_label_punctuation(self):
        data = parse_job_detail((FIXTURES / "detail.html").read_text())
        self.assertEqual(data["education"], "博士")
        self.assertIn(",", data["major"])

    def test_missing_detail_sibling_does_not_capture_next_label(self):
        data = parse_job_detail((FIXTURES / "partial.html").read_text())
        self.assertEqual(data, {"education": "本科及以上", "major": ""})

    def test_no_recognizable_detail_fields_fails(self):
        with self.assertRaises(CollectionError):
            parse_job_detail("<html>Wayback error</html>")

    def test_none_is_missing_but_unrestricted_is_preserved(self):
        self.assertEqual(parse_job_detail('<div class="tr_name">专业</div><div>NoNe</div>')["major"], "")
        self.assertEqual(parse_job_detail('<div class="tr_name">专业</div><div>不限</div>')["major"], "不限")


class RequestTests(unittest.TestCase):
    def test_redirect_cannot_escape_fixed_archive_host_or_path(self):
        for url in ["http://web.archive.org/web/1/https://zp.z2hospital.com/department/detailInfo.action", "https://evil.test/", "https://web.archive.org/anything", "https://user:pass@web.archive.org/", "file:///etc/passwd"]:
            self.assertFalse(allowed_url(url))
        session = Mock()
        session.get.return_value = response(LIST_URL, status=302, headers={"Location": "https://evil.test/"})
        with self.assertRaisesRegex(CollectionError, "重定向"):
            Crawler(retries=0).get_page(session, LIST_URL, lambda *args: None, threading.Event())
        self.assertEqual(session.get.call_count, 1)

    def test_valid_archive_redirect_keeps_timeout_and_disables_auto_redirect(self):
        session = Mock()
        target = LIST_URL.replace("20260515165600", "20260515170000")
        session.get.side_effect = [response(LIST_URL, status=302, headers={"Location": target}), response(target, "hello")]
        self.assertEqual(Crawler().get_page(session, LIST_URL, lambda *args: None, threading.Event()), "hello")
        self.assertEqual(session.get.call_args.kwargs, {"timeout": (5,15), "allow_redirects": False})

    def test_timeout_and_transient_http_retry_is_bounded(self):
        stop = Mock(); stop.is_set.return_value = False; stop.wait.return_value = False
        session = Mock(); session.get.side_effect = requests.Timeout()
        events = []
        with self.assertRaisesRegex(CollectionError, "超时"):
            Crawler(retries=1).get_page(session, LIST_URL, lambda event, value: events.append(event), stop)
        self.assertEqual(session.get.call_count, 2)
        self.assertEqual(events.count("retry"), 1)
        session.get.side_effect = [response(LIST_URL, status=503), response(LIST_URL, "ok")]
        self.assertEqual(Crawler().get_page(session, LIST_URL, lambda *args: None, stop), "ok")

    def test_404_and_ssl_fail_without_retry(self):
        for error in [requests.exceptions.SSLError(), None]:
            session = Mock()
            if error:
                session.get.side_effect = error
            else:
                session.get.return_value = response(LIST_URL, status=404)
            with self.assertRaises(CollectionError):
                Crawler().get_page(session, LIST_URL, lambda *args: None, threading.Event())
            self.assertEqual(session.get.call_count, 1)

    def test_one_timeout_does_not_stop_other_jobs(self):
        session = FixtureSession(error_ids={"imaging": requests.Timeout()})
        events = []
        jobs = FixtureCrawler(session).run(lambda kind, value: events.append((kind,value)))
        self.assertEqual(len(jobs), 12)
        self.assertEqual(sum(job["parse_status"] == "failed" for job in jobs), 3)
        self.assertEqual(len([event for event in events if event[0] == "detail_finished"]), 12)

    def test_stop_event_interrupts_without_fabricated_completion(self):
        stop = threading.Event(); stop.set()
        with self.assertRaises(CollectionStopped):
            FixtureCrawler().run(lambda *args: None, stop)


class APITests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_real_api_to_fixture_parser_to_saved_csv(self):
        with TestClient(create_app(self.directory, FixtureCrawler)) as client:
            task_id = client.post("/api/tasks", json={}).json()["id"]
            task = finished(client, task_id)
            self.assertEqual(task["source_kind"], "local_html_test")
            self.assertEqual([task[key] for key in ["discovered","processed","parsed","failed","complete","incomplete","progress"]], [12,12,10,2,9,1,100])
            self.assertEqual(task["status"], "partial")
            result = client.get(f"/api/tasks/{task_id}/results").json()
            self.assertEqual(len(result["jobs"]), 12)
            self.assertEqual(client.get("/api/results/latest").json()["task_id"], task_id)
            download = client.get(task["download_url"])
            self.assertEqual(download.content[:3], b"\xef\xbb\xbf")
            rows = list(csv.reader(io.StringIO(download.content.decode("utf-8-sig"))))
            self.assertEqual(rows[0], ["岗位名","学历","专业","链接"])
            self.assertEqual(len(rows), 13)
            self.assertIn(",", rows[1][2])
            self.assertEqual(rows[5][1:3], ["none","none"])
            self.assertIn("attachment", download.headers["content-disposition"])

    def test_unknown_progress_duplicate_start_and_other_requests_remain_available(self):
        gate = threading.Event()
        factory = lambda: FixtureCrawler(FixtureSession(gate=gate))
        with TestClient(create_app(self.directory, factory)) as client:
            try:
                first = client.post("/api/tasks", json={}).json()
                current = client.get(f"/api/tasks/{first['id']}").json()
                self.assertIsNone(current["discovered"])
                self.assertIsNone(current["progress"])
                self.assertEqual(current["processed"], 0)
                self.assertEqual(client.post("/api/tasks", json={}).status_code, 409)
                self.assertEqual(client.get(first.get("download_url") or f"/api/tasks/{first['id']}/download").status_code, 409)
                self.assertEqual(client.get("/api/health").status_code, 200)
                threading.Event().wait(.05)
                self.assertEqual(client.get(f"/api/tasks/{first['id']}").json()["processed"], 0)
            finally:
                gate.set()
            finished(client, first["id"])

    def test_fully_parsed_task_completes_and_csv_neutralizes_formulas(self):
        html = '<li class="zp_li" onclick="openDetail(\'imaging\')"><div class="left_name">=1+1</div></li>'
        with TestClient(create_app(self.directory, lambda: FixtureCrawler(FixtureSession(list_html=html)))) as client:
            task_id = client.post("/api/tasks", json={}).json()["id"]
            task = finished(client, task_id)
            self.assertEqual(task["status"], "completed")
            self.assertEqual(task["complete"], 1)
            rows = list(csv.reader(io.StringIO(client.get(task["download_url"]).content.decode("utf-8-sig"))))
            self.assertEqual(rows[1][0], "'=1+1")
            self.assertEqual(client.get(f"/api/tasks/{task_id}/results").json()["jobs"][0]["title"], "=1+1")

    def test_all_detail_failures_still_save_list_and_report_zero_parsed(self):
        html = '<li class="zp_li" onclick="openDetail(\'not-found\')"><div class="left_name">缺失存档岗位</div></li>'
        with TestClient(create_app(self.directory, lambda: FixtureCrawler(FixtureSession(list_html=html)))) as client:
            task_id = client.post("/api/tasks", json={}).json()["id"]
            task = finished(client, task_id)
            self.assertEqual([task["status"], task["parsed"], task["failed"]], ["partial",0,1])
            self.assertTrue(task["result_ready"])

    def test_two_simultaneous_start_requests_only_create_one_task(self):
        gate = threading.Event()
        with TestClient(create_app(self.directory, lambda: FixtureCrawler(FixtureSession(gate=gate)))) as client:
            try:
                with ThreadPoolExecutor(2) as pool:
                    statuses = list(pool.map(lambda _: client.post("/api/tasks", json={}).status_code, range(2)))
                self.assertEqual(sorted(statuses), [202,409])
            finally:
                gate.set()

    def test_failed_new_task_preserves_previous_download_and_survives_restart(self):
        calls = 0
        def factory():
            nonlocal calls
            calls += 1
            return FixtureCrawler(FixtureSession(list_status=404 if calls > 1 else 200))
        with TestClient(create_app(self.directory, factory)) as client:
            first_id = client.post("/api/tasks", json={}).json()["id"]
            first = finished(client, first_id)
            original = client.get(first["download_url"]).content
            second_id = client.post("/api/tasks", json={}).json()["id"]
            second = finished(client, second_id)
            self.assertEqual(second["status"], "failed")
            self.assertIn("404", second["error"])
            self.assertFalse(second["result_ready"])
            self.assertIsNone(second["progress"])
            self.assertEqual(client.get("/api/results/latest").json()["task_id"], first_id)
            self.assertEqual(client.get(first["download_url"]).content, original)
        with TestClient(create_app(self.directory, FixtureCrawler)) as restarted:
            self.assertEqual(restarted.get("/api/tasks").json()["latest_task"]["id"], second_id)
            self.assertEqual(restarted.get(first["download_url"]).content, original)

    def test_recovery_marks_unfinished_task_interrupted(self):
        with TestClient(create_app(self.directory, FixtureCrawler)) as client:
            task_id = client.post("/api/tasks", json={}).json()["id"]
            finished(client, task_id)
        metadata = self.directory / task_id / "task.json"
        value = json.loads(metadata.read_text()); value.update(status="fetching_details", result_ready=False)
        metadata.write_text(json.dumps(value))
        with TestClient(create_app(self.directory, FixtureCrawler)) as client:
            task = client.get(f"/api/tasks/{task_id}").json()
            self.assertEqual(task["status"], "interrupted")
            self.assertFalse(task["result_ready"])

    def test_storage_failure_is_not_reported_as_success(self):
        with patch.object(TaskManager, "_save_results", side_effect=OSError("disk full")):
            with TestClient(create_app(self.directory, FixtureCrawler)) as client:
                task_id = client.post("/api/tasks", json={}).json()["id"]
                task = finished(client, task_id)
                self.assertEqual(task["status"], "failed")
                self.assertIn("写入失败", task["error"])
                self.assertEqual(client.get(f"/api/tasks/{task_id}/download").status_code, 409)

    def test_task_creation_failure_does_not_leave_a_phantom_running_task(self):
        with patch.object(TaskManager, "_persist", side_effect=OSError("disk full")):
            with TestClient(create_app(self.directory, FixtureCrawler)) as client:
                self.assertEqual(client.post("/api/tasks", json={}).status_code, 503)
                self.assertIsNone(client.get("/api/tasks").json()["active_task"])

    def test_malformed_list_is_failure_without_empty_success_csv(self):
        with TestClient(create_app(self.directory, lambda: FixtureCrawler(FixtureSession(list_html="<h1>Not archived</h1>")))) as client:
            task_id = client.post("/api/tasks", json={}).json()["id"]
            task = finished(client, task_id)
            self.assertEqual(task["status"], "failed")
            self.assertEqual(list((self.directory / task_id).glob("*.csv")), [])

    def test_api_cannot_accept_user_url_and_rejects_cross_origin_forms(self):
        with TestClient(create_app(self.directory, FixtureCrawler)) as client:
            self.assertEqual(client.post("/api/tasks", json={"url":"http://example.com"}).status_code, 422)
            self.assertEqual(client.post("/api/tasks", json={}, headers={"Origin":"https://evil.test"}).status_code, 403)
            self.assertEqual(client.post("/api/tasks", content="x=1", headers={"Content-Type":"application/x-www-form-urlencoded"}).status_code, 415)
            self.assertEqual(client.get("/api/tasks/not-an-id/download").status_code, 404)
            for path in ["/team-task.py", "/招聘数据.csv", "/README.md", "/sample.csv"]:
                self.assertEqual(client.get(path).status_code, 404)

    def test_os_file_lock_blocks_a_second_manager(self):
        gate = threading.Event()
        first = TaskManager(self.directory, lambda: FixtureCrawler(FixtureSession(gate=gate)))
        second = None
        try:
            first.start()
            second = TaskManager(self.directory, FixtureCrawler)
            with self.assertRaises(TaskBusy):
                second.start()
        finally:
            gate.set(); first.close()
            if second:
                second.close()


if __name__ == "__main__":
    unittest.main()
