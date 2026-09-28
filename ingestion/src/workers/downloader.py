"""Download URL ingestion requests into the filewatcher's fetched directory and publishes on document_fetched"""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

SRC_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = SRC_DIR.parent.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from common.helpers.configservice import load_config
from common.helpers.kafkahelper import KafkaHelper
from common.helpers.dbrepository import DocumentRepository


config = load_config('ingestion/config/config.yml')

DOWNLOAD_REQUESTED_TOPIC = config['kafka']['download_requested_topic']
DOCUMENT_FETCHED_TOPIC = config['kafka']['document_fetched_topic']
CONSUMER_GROUP = config['downloader']['consumer_group']
FETCHED_DIR = Path(config['staging']["fetched_dir_path"])

document_repository = DocumentRepository()


def download_document(ingestion_id:str, document_id: str, client_id:str, url: str, destination: Path) -> Path:
    if not ingestion_id or not document_id or not url or not url or not destination:
        raise ValueError("ingestion_id, document_id, url, and destination are all required")
    
    parsed = urlparse(url)
    #basic sanity checks
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("url must be HTTP(S)")

    request = Request(url, headers={"User-Agent": "rag-ingestion-downloader"})
    with urlopen(request, timeout=30) as response:
        content_type = (response.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        data = response.read()

    if content_type != "application/pdf":
        raise ValueError(f"URL returned unsupported content type: {content_type or 'missing'}")
    if not data.startswith(b"%PDF"):
        raise ValueError("downloaded content is not a PDF")


    #copy bytes to the fetched directory
    FETCHED_DIR.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)

    return destination


def main() -> None:
    
    kafkahelper = KafkaHelper()
    consumer = kafkahelper.getconsumer(DOWNLOAD_REQUESTED_TOPIC, CONSUMER_GROUP)
    
    for message in consumer:
        event = message.value
        try:
            print(f'download message received: {message}')

            ingestion_id = event.get("ingestion_id") 
            document_id = event.get("document_id")
            client_id = event.get("client_id")
            url = event.get("url")
            dest_file_name = event.get("dest_file_name")
            destination = FETCHED_DIR / dest_file_name

            #download to the fetched directory
            download_document(ingestion_id, document_id, client_id, url, destination)

            #update ingestion record
            document_repository.upsert_ingestion_record(ingestion_id, document_id, client_id, 'in-progress', 'document.fetched')

            #send kafka notification to document.fetched topic
            kafkahelper.send_event(DOCUMENT_FETCHED_TOPIC, {
                'ingestion_id': ingestion_id,
                'document_id': document_id,
                'client_id': client_id,

                "source_type": "url",
                "dest_file_path": str(destination),
                "dest_file_name": destination.name,
                "dest_file_type": destination.suffix,
            })

        except Exception as exc:
            print(f"Failed to download document {event.get('document_id')}: {exc}")

            #udpate ingestion record
            document_repository.upsert_ingestion_record(ingestion_id, document_id, client_id, 'completed', 'download.failed')
            
        finally:
            #todo: add retry logic and/or DLQ processing
            consumer.commit()


if __name__ == "__main__":
    main()
