import os
import json
from time import time
from typing import Any
from kafka import KafkaProducer, KafkaConsumer

class KafkaHelper:
    def __init__(self, bootstrap_servers: str | None = None):
        self.bootstrap_servers = bootstrap_servers 
        if not self.bootstrap_servers:
            self.bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")

        self._producer = None
        
    @property
    def producer(self):
        if self._producer is None:
            self._producer = KafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=lambda value: json.dumps(value).encode(),
            )
        return self._producer

    def send_event(self, topic:str, event: dict[str, Any], retry_cnt=3) -> None:
        for attempt in range(retry_cnt):
            try:
                future = self.producer.send(topic, value=event)
                metadata = future.get(timeout=10)
                print(
                    f"Published event to topic={metadata.topic}, "
                    f"partition={metadata.partition}, "
                    f"offset={metadata.offset}"
                )
                return
            except Exception as e:
                print(f"Failed to send event on attempt {attempt + 1}: {e}")
                time.sleep(2**attempt)  # exp Wait before retrying

        print("All attempts to send event failed.")
        #todo: add logic to push this to a dead letter topic or to some other durable log to avoid losing the event


    def getconsumer(self, topic, group_id, auto_offset_reset='latest', enable_auto_commit=True) -> KafkaConsumer:
        consumer = (KafkaConsumer(
            topic,
            bootstrap_servers=self.bootstrap_servers,
            value_deserializer=lambda value: json.loads(value.decode("utf-8")),
            group_id=group_id,
            auto_offset_reset=auto_offset_reset,
            enable_auto_commit=enable_auto_commit,
        ))
        return consumer
