from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Final, Optional

from blinker import Namespace

EV_DATA: Final[str] = "data"
EV_SNAPSHOT: Final[str] = "snapshot"
EV_ORDER_CMD: Final[str] = "order_cmd"
EV_ORDER_ACK: Final[str] = "order_ack"
EV_ORDER_REJECT: Final[str] = "order_reject"
EV_TRADE: Final[str] = "trade"
EV_AUDIT: Final[str] = "audit"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def new_event(
    ev: str,
    payload: Dict[str, Any],
    *,
    key: Optional[str] = None,
    src: str,
    eid: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "id": eid or str(uuid.uuid4()),
        "type": ev,
        "ts": _now(),
        "source": src,
        "key": key,
        "payload": payload,
        "schema": "market.event.v1",
    }


class EventHub:
    """Single in-process event hub built on blinker."""

    def __init__(self):
        self._ns = Namespace()
        self._subs: Dict[str, Dict[str, Callable[..., Any]]] = {}

    def signal(self, ev: str):
        return self._ns.signal(ev)

    def on(
        self,
        ev: str,
        fn: Callable[[Dict[str, Any]], Any],
        *,
        name: Optional[str] = None,
    ) -> str:
        sid = name or str(uuid.uuid4())

        def recv(sender, **kwargs):
            fn(kwargs.get("event"))

        self.signal(ev).connect(recv, weak=False)
        self._subs.setdefault(ev, {})[sid] = recv
        return sid

    def off(self, ev: str, sid: str) -> None:
        recv = self._subs.get(ev, {}).pop(sid, None)
        if recv is None:
            return
        self.signal(ev).disconnect(recv)

    def emit(
        self,
        ev: str,
        payload: Dict[str, Any],
        *,
        key: Optional[str] = None,
        src: str,
        eid: Optional[str] = None,
        with_audit: bool = True,
    ) -> Dict[str, Any]:
        msg = new_event(ev, payload, key=key, src=src, eid=eid)
        self.signal(ev).send(self, event=msg)

        if with_audit and ev != EV_AUDIT:
            audit_payload = {
                "event_id": msg["id"],
                "event_type": msg["type"],
                "event_key": msg.get("key"),
                "event_ts": msg.get("ts"),
                "source": msg.get("source"),
                "payload": msg.get("payload"),
            }
            audit = new_event(EV_AUDIT, audit_payload, key=str(msg["id"]), src="audit")
            self.signal(EV_AUDIT).send(self, event=audit)
        return msg

    def push(self, msg: Dict[str, Any], *, with_audit: bool = False) -> None:
        ev = str(msg.get("type") or "")
        if not ev:
            return
        self.signal(ev).send(self, event=msg)
        if with_audit and ev != EV_AUDIT:
            self.emit(
                EV_AUDIT,
                {
                    "event_id": msg.get("id"),
                    "event_type": msg.get("type"),
                    "event_key": msg.get("key"),
                    "event_ts": msg.get("ts"),
                    "source": msg.get("source"),
                    "payload": msg.get("payload"),
                },
                key=str(msg.get("id") or ""),
                src="audit",
                with_audit=False,
            )

    def clear(self) -> None:
        for ev, mp in list(self._subs.items()):
            for sid in list(mp.keys()):
                self.off(ev, sid)
