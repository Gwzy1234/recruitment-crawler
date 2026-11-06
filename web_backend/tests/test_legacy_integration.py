"""Verify that real legacy crawler functions are used by the Web backend, offline."""
import ast
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from web_backend.app import create_app
from web_backend.legacy_adapter import LegacyCrawler, legacy

ROOT = Path(__file__).resolve().parents[2]
LIST_HTML = '''<ul><li class="zp_li" onclick="show('r1')"><div class="left_name">医学影像技师</div></li>
<li class="zp_li" onclick="show('r2')"><div class="left_name">放射科医师</div></li></ul>'''
DETAIL_HTML = '''<div class="tr_name">学历学位</div><div>本科及以上</div>
<div class="tr_name">专业</div><div>医学影像技术</div>'''

class LegacyIntegrationTests(unittest.TestCase):
    def test_original_three_functions_unchanged(self):
        def definitions(path):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            return {n.name: ast.dump(n, include_attributes=False) for n in tree.body
                    if isinstance(n, ast.FunctionDef)}
        original = definitions(ROOT / 'team-task-original.py')
        current = definitions(ROOT / 'team-task.py')
        for name in ('get_page', 'parse_job_list', 'parse_job_detail'):
            self.assertEqual(current[name], original[name], name)

    def test_web_request_calls_actual_original_parser_and_saves_results(self):
        calls = []
        def page(url):
            calls.append(url)
            if 'detailInfomore.action' in url:
                return LIST_HTML
            if 'uuid=r1' in url:
                return DETAIL_HTML
            if 'uuid=r2' in url:
                return '<html>存档无法读取</html>'
            raise AssertionError('Unknown URL: ' + url)

        with tempfile.TemporaryDirectory() as directory:
            with patch.object(legacy, 'get_page', side_effect=page), \
                 patch.object(legacy, 'parse_job_list', wraps=legacy.parse_job_list) as list_parser, \
                 patch.object(legacy, 'parse_job_detail', wraps=legacy.parse_job_detail) as detail_parser:
                with TestClient(create_app(Path(directory), lambda: LegacyCrawler(interval=0))) as client:
                    self.assertEqual(client.get('/api/health').status_code, 200)
                    task_id = client.post('/api/tasks', json={}).json()['id']
                    for _ in range(300):
                        task = client.get(f'/api/tasks/{task_id}').json()
                        if task['status'] in ('completed', 'partial', 'failed', 'interrupted'):
                            break
                        time.sleep(0.01)
                    self.assertEqual(task['status'], 'partial', task)
                    self.assertEqual(task['source_kind'], 'wayback_team_task')
                    self.assertEqual((task['discovered'],task['parsed'],task['failed']), (2,1,1))
                    self.assertTrue(task['result_ready'])
                    payload = client.get(f'/api/tasks/{task_id}/results').json()
                    self.assertEqual(payload['jobs'][0]['title'], '医学影像技师')
                    self.assertEqual(payload['jobs'][0]['education'], '本科及以上')
                    self.assertEqual(payload['jobs'][1]['parse_status'], 'failed')
                    csv_data = client.get(task['download_url']).content.decode('utf-8-sig')
                    self.assertIn('医学影像技师', csv_data)
                    self.assertEqual(list_parser.call_count,1)
                    self.assertEqual(detail_parser.call_count,2)
                    self.assertEqual(len(calls),3)

if __name__ == '__main__':
    unittest.main()
