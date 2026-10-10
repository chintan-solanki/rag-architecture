"""Download URL ingestion requests into the filewatcher's fetched directory and publishes on document_fetched"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen
import ssl
import certifi

SRC_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = SRC_DIR.parent.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from common.helpers.configservice import load_config
from common.helpers.kafkahelper import KafkaHelper
from common.helpers.dbrepository import DocumentRepository
from common.helpers.ingestionstate import IngestionDocumentState
from common.helpers.redishelper import RedisHelper


config = load_config('ingestion/config/config.yml')

URL_REQUESTED_TOPIC = config['kafka']['url_requested_topic']
DOCUMENT_FETCHED_TOPIC = config['kafka']['document_fetched_topic']
CONSUMER_GROUP = config['downloader']['consumer_group']
FETCHED_DIR = Path(config['staging']["fetched_dir_path"])

document_repository = DocumentRepository()
redis_helper = RedisHelper().__enter__()

# Create a custom SSL context using certifi's bundle
# this is to avoid certificate verification issues when downloading from HTTPS URLs
#context = ssl.create_default_context(cafile=certifi.where()) 
context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)

def safe_file_name(name: str) -> str:
    clean_name = Path(name).name
    clean_name = re.sub(r"[^A-Za-z0-9._-]", "_", clean_name)
    return clean_name if clean_name.lower().endswith(".pdf") else f"{clean_name}.pdf"


def download_document(ingestion_id:str, document_id: str, client_id:str, url: str, destination: Path) -> Path:
    if not ingestion_id or not document_id or not url or not url or not destination:
        raise ValueError("ingestion_id, document_id, url, and destination are all required")

    parsed = urlparse(url)
    #basic sanity checks
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("url must be HTTP(S)")

    request = Request(url, headers={"User-Agent": "rag-ingestion-downloader"})

    with urlopen(request, timeout=30, context=context) as response:
        content_type = (response.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        data = response.read()

    if content_type != "application/pdf":
        raise ValueError(f"URL returned unsupported content type: {content_type or 'missing'}")
    if not data.startswith(b"%PDF"):
        raise ValueError("downloaded content is not a PDF")

    #copy bytes to the ingestion-specific folder under the fetched directory
    FETCHED_DIR.mkdir(parents=True, exist_ok=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)

    return destination


def main() -> None:
    
    kafkahelper = KafkaHelper()
    consumer = kafkahelper.getconsumer(URL_REQUESTED_TOPIC, CONSUMER_GROUP)
    
    for message in consumer:
        ingestion_document_state = None

        event = message.value
        try:
            
            print(f'download message received: {message}')

            ingestion_id = event.get("ingestion_id") 
            document_id = event.get("document_id")
            original_file_name = event.get("original_file_name")
            ingestion_config = event.get("ingestion_config")
            client_id = event.get("client_id")
            url = event.get("url")
            dest_file_name = event.get("dest_file_name") or "document.pdf"
            dest_directory = Path(event.get("dest_directory") or (FETCHED_DIR / ingestion_id))
            destination = dest_directory / safe_file_name(dest_file_name)

            #create new ingestion document state for this ingestion message
            ingestion_document_state = IngestionDocumentState(document_repository, redis_helper, ingestion_id, document_id, client_id)

            #download to the fetched directory
            download_document(ingestion_id, document_id, client_id, url, destination)

            #update ingestion record
            ingestion_document_state.RecordState(status='in-progress', stage='document has been downloaded')

            #send kafka notification to document.fetched topic
            kafkahelper.send_event(DOCUMENT_FETCHED_TOPIC, {
                'ingestion_id': ingestion_id,
                'document_id': document_id,
                'original_file_name': original_file_name,
                'ingestion_config': ingestion_config,
                'client_id': client_id,

                "source_type": "url",
                "dest_file_path": str(destination),
                "dest_file_name": destination.name,
                "dest_file_type": destination.suffix,
            })

        except Exception as exc:
            print(f"Failed to download document {event.get('document_id')}: {exc}")

            # update ingestion record
            if ingestion_document_state:
                ingestion_document_state.RecordState(status='failed', stage='document download failed', error=f'{exc}')

        finally:
            #todo: add retry logic and/or DLQ processing
            consumer.commit()


if __name__ == "__main__":
    main()
