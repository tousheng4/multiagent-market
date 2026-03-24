from __future__ import annotations

import json
import threading
from typing import Dict, Optional

from .dispatchers import Seen
from .event_hub import (EV_AUDIT, EV_ORDER_ACK, EV_ORDER_CMD, EV_ORDER_REJECT,
                        EV_SNAPSHOT, EV_TRADE, EventHub)


def _load_kafka():
    try:
        from kafka import KafkaConsumer, KafkaProducer  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "kafka-python is required for KafkaBridge. Install with: uv add kafka-python"
        ) from exc
    return KafkaProducer, KafkaConsumer


class KafkaBridge:
    """Bridge between blinker events and Kafka topics for stage-3."""

    def __init__(
        self,
        hub: EventHub,
        servers: str = "localhost:9092",
        group: str = "multiagent-market",
        client: str = "market-bridge",
    ):
        Producer, Consumer = _load_kafka()
        self.hub = hub
        self._producer = Producer(
            bootstrap_servers=servers,
            value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode(
                "utf-8"
            ),
        )
        self._consumer = Consumer(
            bootstrap_servers=servers,
            group_id=group,
            client_id=client,
            value_deserializer=lambda b: json.loads(b.decode("utf-8")),
            auto_offset_reset="earliest",
            enable_auto_commit=True,
        )

        self.topics = {
            EV_ORDER_CMD: "orders",
            EV_ORDER_ACK: "orders",
            EV_ORDER_REJECT: "orders",
            EV_TRADE: "trades",
            EV_SNAPSHOT: "snapshots",
            EV_AUDIT: "audit",
        }

        self._pub_ids: Dict[str, str] = {}
        self._seen = Seen()
        self._run = False
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start_publish(self) -> None:
        for ev in self.topics.keys():
            sid = self.hub.on(
                ev, lambda msg, ev=ev: self._to_kafka(ev, msg), name=f"kafka_pub_{ev}"
            )
            self._pub_ids[ev] = sid

    def _to_kafka(self, ev: str, msg: Dict) -> None:
        topic = self.topics[ev]
        self._producer.send(topic, msg)

    def start_order_consumer(self) -> None:
        if self._run:
            return
        self._run = True
        self._stop.clear()
        self._consumer.subscribe(["orders"])
        self._thread = threading.Thread(target=self._poll, daemon=True)
        self._thread.start()

    def _poll(self) -> None:
        while not self._stop.is_set():
            polled = self._consumer.poll(timeout_ms=200)
            for records in polled.values():
                for rec in records:
                    msg = rec.value
                    if not isinstance(msg, dict):
                        continue
                    if msg.get("type") != EV_ORDER_CMD:
                        continue
                    mid = str(msg.get("id") or "")
                    if self._seen.has(mid):
                        continue
                    self.hub.push(msg, with_audit=True)
                    self._seen.add(mid)

    def close(self) -> None:
        for ev, sid in list(self._pub_ids.items()):
            self.hub.off(ev, sid)
        self._pub_ids.clear()

        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)

        try:
            self._producer.flush(timeout=2)
        except Exception:
            pass

        self._producer.close()
        self._consumer.close()
