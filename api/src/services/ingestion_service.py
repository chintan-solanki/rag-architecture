import re
from typing import Any
import uuid
from pathlib import Path
from urllib.parse import urlparse
from fastapi import UploadFile

from common.helpers.kafkahelper import KafkaHelper
from common.helpers.dbrepository import DocumentRepository

class IngestionService:
    def __init__(self, config:Any, fetched_dir:Path):

        self.config = config

        self.fetched_dir = fetched_dir

        self.kafkahelper = KafkaHelper()
        self.document_fetched_topic = config['kafka']['document_fetched_topic']
        self.download_requested_topic = config['kafka']['download_requested_topic']

        self.document_repository = DocumentRepository()

    @staticmethod
    def _safe_name(name: str) -> str:
        name = Path(name).name
        name = re.sub(r"[^A-Za-z0-9._-]", "_", name)
        return name if name.lower().endswith(".pdf") else f"{name}.pdf"

    async def accept_upload(self, upload: UploadFile, client_id: str) -> str:
        if upload.content_type != "application/pdf" and not (upload.filename or "").lower().endswith(".pdf"):
            raise ValueError("a PDF upload is required")
        
        file_stem, file_suffix = upload.filename[:-4], upload.filename[-4:].replace('/', '_')
        
        #generate a random ingestion id
        ingestion_id = uuid.uuid4().hex
        document_id = f'{ingestion_id}_{file_stem}'
        
        #retrieve the file content and check if the file is indeed a pdf
        data = await upload.read()
        
        if not data.startswith(b"%PDF"):
            raise ValueError("uploaded content is not a PDF")

        #create ingestion record in db
        self.document_repository.upsert_ingestion_record(ingestion_id, document_id, client_id, 'in-progress', 'upload_requested')

        #upload the file in fetched directory
        self.fetched_dir.mkdir(parents=True, exist_ok=True)
        destination = self.fetched_dir / f"{ingestion_id}_{self._safe_name(upload.filename or 'document.pdf')}"
        destination.write_bytes(data)

        #send kafka document.fetched event directly
        self.kafkahelper.send_event(self.document_fetched_topic, {
            'ingestion_id': ingestion_id,
            'document_id': document_id,
            'client_id': client_id,

            "source_type": "upload",
            "dest_file_path": str(destination),
            "dest_file_name": destination.name,
            "dest_file_type": destination.suffix,
        })

        print(f'document uploaded with document id {document_id}')

        return ingestion_id

    def accept_url(self, url: str, client_id: str) -> str:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("url must be HTTP(S)")
        
        #generate a random ingestion id
        ingestion_id = uuid.uuid4().hex
        file_stem = f'{parsed.hostname}{parsed.path}'.replace('/', '_')
        document_id = f'{ingestion_id}_{file_stem}'
        dest_file_name = f'{document_id}.pdf'
        
        #create ingestion record in db
        self.document_repository.upsert_ingestion_record(ingestion_id, document_id, client_id, 'in-progress', 'download_requested')
        
        #publish to kafka 'download_topic' 
        self.kafkahelper.send_event(self.download_requested_topic, {
            "ingestion_id": ingestion_id, 
            "document_id": document_id, 
            "client_id" : client_id,
            "url": url,
            "dest_file_name": dest_file_name
            }
        )

        return ingestion_id
