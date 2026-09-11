from kafka import KafkaProducer, KafkaConsumer
import os
import json
import time

KAFKA_BOOTSTRAP_SERVERS = "kafka:9092"

class KafkaHelper:

    def __init__(self):
        
        self.bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", KAFKA_BOOTSTRAP_SERVERS)

        self.producer = KafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
            value_serializer=lambda value: json.dumps(value).encode("utf-8"),
        )

    def send_event(self, topic, event, retry_cnt=3):
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


    def getconsumer(self, topic, group_id) -> KafkaConsumer:
        consumer = (KafkaConsumer(
            topic,
            bootstrap_servers=self.bootstrap_servers,
            value_deserializer=lambda value: json.loads(value.decode("utf-8")),
            group_id=group_id,
            auto_offset_reset="earliest",
            enable_auto_commit=False,
            
        ))
        return consumer

    
