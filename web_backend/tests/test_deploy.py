"""Deployment host validation without hitting the network."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from web_backend.app import create_app

class DeployHostTests(unittest.TestCase):
    def test_public_host_allows_secure_requests_and_rejects_wrong_origin(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"PUBLIC_HOSTNAME": "jobs.example.test"}):
            with TestClient(create_app(Path(directory))) as client:
                ok = client.get('/api/health', headers={"host":"jobs.example.test"})
                self.assertEqual(ok.status_code, 200)
                denied = client.post('/api/tasks', content='{}', headers={
                    "host":"jobs.example.test", "origin":"https://evil.example.test", "content-type":"application/json"})
                self.assertEqual(denied.status_code, 403)
                forbidden = client.get('/api/health', headers={"host":"evil.example.test"})
                self.assertEqual(forbidden.status_code, 400)

    def test_empty_public_host_keeps_local_access(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"PUBLIC_HOSTNAME":""}):
            with TestClient(create_app(Path(directory))) as client:
                self.assertEqual(client.get('/api/health').status_code, 200)

if __name__ == '__main__':
    unittest.main()
