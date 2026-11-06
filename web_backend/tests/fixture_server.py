"""Explicit local-HTML integration server. Not a real Wayback crawl.

Run: python -m web_backend.tests.fixture_server --port 8766
First task: mixed fixture outcome. Second task: list HTTP 404. Later: mixed outcome.
"""
import argparse
from pathlib import Path

import uvicorn

from web_backend.app import create_app
from web_backend.tests.support import FixtureCrawler, FixtureSession


def main():
    parser = argparse.ArgumentParser(description="LOCAL HTML TEST ONLY — does not contact the recruitment website")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--data-dir", type=Path, required=True)
    args = parser.parse_args()
    runs = 0

    def factory():
        nonlocal runs
        runs += 1
        return FixtureCrawler(FixtureSession(list_status=404 if runs == 2 else 200, delay=.25), interval=.1)

    print("LOCAL HTML FIXTURE TEST SERVER — NO REAL WEBSITE REQUESTS", flush=True)
    uvicorn.run(create_app(args.data_dir, factory), host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
