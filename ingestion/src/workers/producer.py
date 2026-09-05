import json
import time

from kafka import KafkaProducer

KAFKA_BOOTSTRAP_SERVERS = "kafka:9092"
TOPIC = "test-events"

producer = KafkaProducer(
    bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
    value_serializer=lambda value: json.dumps(value).encode("utf-8"),
)

for i in range(10):
    event = {
        "event_id": i,
        "message": f"Hello from producer {i}",
    }

    future = producer.send(TOPIC, value=event)

    # Wait for Kafka to acknowledge the message.
    metadata = future.get(timeout=10)

    print(
        f"Published event {i} "
        f"to topic={metadata.topic}, "
        f"partition={metadata.partition}, "
        f"offset={metadata.offset}"
    )

    time.sleep(2)


producer.flush()
producer.close()

print("Producer finished.")