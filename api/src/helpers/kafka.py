import json
import os
from typing import Any
from ..services.configservice import load_config


class KafkaPublisher:
    def __init__(self, config, bootstrap_servers: str | None = None):
        self.config = config
        self.bootstrap_servers = bootstrap_servers or config['kafka']['bootstrap_servers']
        self._producer = None

    @property
    def producer(self):
        if self._producer is None:
            from kafka import KafkaProducer
            self._producer = KafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=lambda value: json.dumps(value).encode(),
            )
        return self._producer

    def publish(self, topic: str, event: dict[str, Any]) -> None:
        self.producer.send(topic, event).get(timeout=10)
