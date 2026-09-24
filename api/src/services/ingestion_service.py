import re
import uuid
from pathlib import Path
from urllib.parse import urlparse
from fastapi import UploadFile
from ..helpers.kafka import KafkaPublisher


class IngestionService:
    def __init__(self, config, incoming_dir: str | Path | None = None, publisher=None, download_topic: str | None = None):
        self.config = config
        self.incoming_dir = Path(incoming_dir or config['staging']['incoming_dir'])

        self.publisher = publisher or KafkaPublisher(config)
        self.download_topic = download_topic or config['kafka']['download_topic']

    @staticmethod
    def _safe_name(name: str) -> str:
        name = Path(name).name
        name = re.sub(r"[^A-Za-z0-9._-]", "_", name)
        return name if name.lower().endswith(".pdf") else f"{name}.pdf"

    async def accept_upload(self, upload: UploadFile) -> str:
        if upload.content_type != "application/pdf" and not (upload.filename or "").lower().endswith(".pdf"):
            raise ValueError("a PDF upload is required")
        document_id = uuid.uuid4().hex
        self.incoming_dir.mkdir(parents=True, exist_ok=True)
        destination = self.incoming_dir / f"{document_id}_{self._safe_name(upload.filename or 'document.pdf')}"
        data = await upload.read()
        if not data.startswith(b"%PDF"):
            raise ValueError("uploaded content is not a PDF")
        destination.write_bytes(data)
        return document_id

    def accept_url(self, url: str) -> str:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("url must be HTTP(S)")
        document_id = uuid.uuid4().hex
        self.publisher.publish(self.download_topic, {"document_id": document_id, "url": url})
        return document_id
