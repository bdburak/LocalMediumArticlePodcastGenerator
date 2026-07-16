import queue
import threading
import uuid
import traceback
from typing import Any, Callable, Dict


class JobQueue:
    def __init__(self) -> None:
        self._jobs: Dict[str, dict] = {}
        self._q: queue.Queue = queue.Queue()
        t = threading.Thread(target=self._worker, daemon=True)
        t.start()

    def submit(self, fn: Callable, **kwargs) -> str:
        jid = uuid.uuid4().hex[:12]
        self._jobs[jid] = {
            "status": "queued",
            "progress": 0,
            "result": None,
            "error": None,
        }
        self._q.put((jid, fn, kwargs))
        return jid

    def get(self, jid: str) -> dict | None:
        return self._jobs.get(jid)

    def _worker(self) -> None:
        while True:
            jid, fn, kwargs = self._q.get()

            def report(pct: int) -> None:
                if jid in self._jobs:
                    self._jobs[jid]["progress"] = pct

            self._jobs[jid]["status"] = "processing"
            kwargs["_report"] = report

            try:
                result = fn(**kwargs)
                self._jobs[jid] = {
                    "status": "done",
                    "progress": 100,
                    "result": result,
                    "error": None,
                }
            except Exception:
                self._jobs[jid] = {
                    "status": "failed",
                    "progress": self._jobs[jid].get("progress", 0),
                    "result": None,
                    "error": traceback.format_exc(),
                }
