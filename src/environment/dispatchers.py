from __future__ import annotations

import asyncio
import json
import os
import threading
import uuid
from collections import deque
from typing import Any, Callable, Deque, Dict, Optional, Set

from .event_hub import EventHub


class QueueDispatcher:
    """Async handler dispatch over asyncio.Queue, fed by blinker events."""

    def __init__(self, hub: EventHub, maxsize: int = 4096):
        self.hub = hub
        self.maxsize = maxsize
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._subs: Dict[str, Dict[str, Any]] = {}

    def _run(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    async def _worker(
        self, q: asyncio.Queue, fn: Callable[[Dict[str, Any]], Any]
    ) -> None:
        while True:
            msg = await q.get()
            try:
                ret = fn(msg)
                if asyncio.iscoroutine(ret):
                    await ret
            except Exception:
                pass
            finally:
                q.task_done()

    def on(
        self,
        ev: str,
        fn: Callable[[Dict[str, Any]], Any],
        *,
        name: Optional[str] = None,
    ) -> str:
        sid = name or str(uuid.uuid4())
        q: asyncio.Queue = asyncio.Queue(maxsize=self.maxsize)
        fut = asyncio.run_coroutine_threadsafe(self._worker(q, fn), self._loop)

        def enqueue(msg: Dict[str, Any]) -> None:
            def put_one() -> None:
                try:
                    q.put_nowait(msg)
                except asyncio.QueueFull:
                    pass

            self._loop.call_soon_threadsafe(put_one)

        hub_sid = self.hub.on(ev, enqueue, name=f"{sid}_hub")
        self._subs[sid] = {"ev": ev, "hub_sid": hub_sid, "fut": fut, "q": q}
        return sid

    def flush(self, timeout: float = 2.0) -> None:
        queues = [sub["q"] for sub in self._subs.values()]
        if not queues:
            return

        async def drain() -> None:
            await asyncio.gather(*(q.join() for q in queues))

        fut = asyncio.run_coroutine_threadsafe(drain(), self._loop)
        try:
            fut.result(timeout=timeout)
        except Exception:
            pass

    def off(self, sid: str) -> None:
        sub = self._subs.pop(sid, None)
        if not sub:
            return
        self.hub.off(sub["ev"], sub["hub_sid"])
        sub["fut"].cancel()
        try:
            sub["fut"].result(timeout=0.5)
        except Exception:
            pass

    def close(self) -> None:
        self.flush(timeout=2.0)
        for sid in list(self._subs.keys()):
            self.off(sid)

        async def shutdown() -> None:
            tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

        fut = asyncio.run_coroutine_threadsafe(shutdown(), self._loop)
        try:
            fut.result(timeout=1)
        except Exception:
            pass
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=2)


class Seen:
    def __init__(self, cap: int = 100_000):
        self.cap = cap
        self._set: Set[str] = set()
        self._q: Deque[str] = deque()

    def has(self, key: Optional[str]) -> bool:
        return bool(key) and key in self._set

    def add(self, key: Optional[str]) -> None:
        if not key or key in self._set:
            return
        self._set.add(key)
        self._q.append(key)
        while len(self._q) > self.cap:
            old = self._q.popleft()
            self._set.discard(old)


class Idem:
    def __init__(
        self,
        fn: Callable[[Dict[str, Any]], Any],
        key_fn: Optional[Callable[[Dict[str, Any]], Optional[str]]] = None,
    ):
        self.fn = fn
        self.key_fn = key_fn or (lambda m: str(m.get("id") or m.get("key") or ""))
        self.seen = Seen()

    def __call__(self, msg: Dict[str, Any]) -> None:
        key = self.key_fn(msg)
        if self.seen.has(key):
            return
        self.fn(msg)
        self.seen.add(key)


class AuditWriter:
    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        self._seen = Seen()

    def write(self, msg: Dict[str, Any]) -> None:
        mid = str(msg.get("id") or msg.get("payload", {}).get("event_id") or "")
        if self._seen.has(mid):
            return

        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        line = json.dumps(msg, ensure_ascii=False)
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line)
                f.write("\n")
        self._seen.add(mid)


class RiskWatcher:
    def __init__(self):
        self.flags = []

    def on_order(self, msg: Dict[str, Any]) -> None:
        payload = msg.get("payload") or {}
        qty = payload.get("quantity")
        if isinstance(qty, int) and qty > 1_000_000:
            self.flags.append({"event_id": msg.get("id"), "reason": "qty_limit"})
