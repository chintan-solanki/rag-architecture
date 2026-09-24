"""Download URL ingestion requests into the filewatcher's incoming directory."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

SRC_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = SRC_DIR.parent.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from helpers.configservice import load_config
from helpers.kafkahelper import KafkaHelper


config = load_config()["downloader"]
TOPIC = config["kafka_subscribe_topic"]
CONSUMER_GROUP = config["kafka_subscribe_consumer_group"]
INCOMING_DIR = ROOT_DIR / config["incoming_dir_rel_path"]

_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]")


def filename_from_url(url: str) -> str:
    """Return a safe PDF filename derived from a URL path."""
    name = Path(unquote(urlparse(url).path)).name or "document.pdf"
    name = _SAFE_FILENAME.sub("_", name)
    return name if name.lower().endswith(".pdf") else f"{name}.pdf"


def download_document(document_id: str, url: str) -> Path:
    if not document_id or not url:
        raise ValueError("document_id and url are required")
    parsed = urlparse(url)
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

    INCOMING_DIR.mkdir(parents=True, exist_ok=True)
    destination = INCOMING_DIR / f"{document_id}_{filename_from_url(url)}"
    destination.write_bytes(data)
    return destination


def main() -> None:
    kafka_helper = KafkaHelper()
    consumer = kafka_helper.getconsumer(TOPIC, CONSUMER_GROUP)
    for message in consumer:
        event = message.value
        try:
            download_document(event.get("document_id"), event.get("url"))
        except Exception as exc:
            print(f"Failed to download document {event.get('document_id')}: {exc}")
        finally:
            consumer.commit()


if __name__ == "__main__":
    main()
