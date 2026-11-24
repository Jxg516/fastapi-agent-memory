"""Smoke test: start the app on a temp DB, then exercise health + write + search."""

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PORT = 8766
BASE = f"http://127.0.0.1:{PORT}"


def call(method: str, path: str, payload: dict | None = None) -> tuple[int, object]:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            return res.status, json.loads(res.read().decode())
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read().decode())


def wait_ready(proc: subprocess.Popen, timeout: float = 25) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError("server exited before becoming ready")
        try:
            status, _ = call("GET", "/health")
            if status == 200:
                return
        except OSError:
            pass
        time.sleep(0.4)
    raise TimeoutError("server did not become ready")


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, "MEMORY_DB": str(Path(tmp) / "smoke.db")}
        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "main:app", "--port", str(PORT)],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            wait_ready(proc)
            print("health:", call("GET", "/health"))

            first = call(
                "POST",
                "/memories",
                {
                    "content": "生产部署必须走蓝绿发布，回滚窗口五分钟",
                    "tags": ["部署", "ops"],
                    "importance": 5,
                },
            )
            print("post high-importance:", first)
            second = call(
                "POST",
                "/memories",
                {
                    "content": "周五下午尽量不要上线新功能",
                    "tags": ["发布", "习惯"],
                    "importance": 2,
                },
            )
            print("post low-importance:", second)

            query = urllib.parse.quote("部署")
            status, hits = call("GET", f"/memories/search?q={query}")
            print("search first:", status, hits)
            assert status == 200 and hits, "search should return at least one hit"
            assert hits[0]["id"] == first[1]["id"], "higher-importance memory should rank first"
            scores = [hit["score"] for hit in hits]
            assert scores == sorted(scores, reverse=True), "hits must be score-descending"

            status, hits_again = call("GET", f"/memories/search?q={query}")
            print("search second:", status, hits_again)
            before = {hit["id"]: hit["use_count"] for hit in hits}
            after = {hit["id"]: hit["use_count"] for hit in hits_again}
            assert after[first[1]["id"]] == before[first[1]["id"]] + 1, "use_count should increment"

            print("list:", call("GET", "/memories"))
            print("SMOKE PASSED")
            return 0
        finally:
            proc.terminate()
            try:
                output, _ = proc.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                output, _ = proc.communicate()
            print("--- server log ---")
            print(output)


if __name__ == "__main__":
    raise SystemExit(main())
