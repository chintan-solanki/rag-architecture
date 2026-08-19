import json

from kafka import KafkaConsumer


KAFKA_BOOTSTRAP_SERVERS = "kafka:9092"
TOPIC = "document_fetched"

consumer = KafkaConsumer(
    TOPIC,
    bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
    group_id="test-consumer-group",
    auto_offset_reset="earliest",
    enable_auto_commit=True,
    value_deserializer=lambda value: json.loads(value.decode("utf-8")),
)

print("Consumer started.")

for message in consumer:
    print(
        f"Received event: {message.value} "
        f"(partition={message.partition}, offset={message.offset})"
    )

