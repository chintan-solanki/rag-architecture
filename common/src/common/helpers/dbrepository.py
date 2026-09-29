import json
import sqlite3
import datetime
from pathlib import Path

class DocumentRepository:
    def __init__(self, db_path=None):
        
        if not db_path:
            ROOT_DIR = Path(__file__).resolve().parents[4]
            db_path = ROOT_DIR / 'database/rag.db'

        self.db_path = str(db_path)

        print(f'db_path = {self.db_path}')
        
        self.create_schema()

    def create_schema(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS documents (
                    document_id TEXT PRIMARY KEY,
                    content_hash TEXT NOT NULL UNIQUE,
                    content_length INTEGER NOT NULL,
                    
                    metadata TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS ingestions (
                    ingestion_id TEXT PRIMARY KEY,
                    document_id TEXT,
                    client_id TEXT,

                    status TEXT NOT NULL,
                    stage TEXT NOT NULL,

                    error TEXT,

                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,

                    FOREIGN KEY (document_id) REFERENCES documents(document_id)
                );

                CREATE INDEX IF NOT EXISTS idx_ingestions_client_status
                    ON ingestions(client_id, status);
            """)

    #returns document by hash (for duplicate check)
    def find_by_hash(self, content_hash):
        record = None
        with sqlite3.connect(self.db_path) as conn:
            record = conn.execute(
                """
                SELECT document_id, content_length
                FROM documents
                WHERE content_hash = ?
                """,
                (content_hash,),
            ).fetchone()

        if record:
            return {
                "document_id": record[0],
                "content_length": record[1],
            }
        
        return None

    #inserts a document record (if it doesn't already exists)
    def insert_or_ignore(self, document_id, content_hash, content_length, metadata={}):

        record = None

        metadata_str = json.dumps(metadata) if metadata else '{}' 

        with sqlite3.connect(self.db_path) as conn:
            
            record = conn.execute(
                """
                INSERT OR IGNORE INTO documents
                    (document_id, content_hash, content_length, metadata)
                VALUES (?, ?, ?, ?)
                RETURNING document_id;
                """,
                (document_id, content_hash, content_length, metadata_str),
            ).fetchone()
        
        if record:
            return record[0]

        return None

    #fetches document by id
    def get_document(self, document_id):

        record = None
        with sqlite3.connect(self.db_path) as conn:
            record = conn.execute(
                """
                SELECT document_id, content_hash, content_length, metadata, created_at
                FROM documents
                WHERE document_id = ?
                """,
                (document_id,),
            ).fetchone()

            if record:
                return  {
                    "document_id": record[0],
                    "content_hash": record[1],
                    "content_length": record[2],
                    "metadata": json.loads(record[3]) if record[3] else {},
                    "created_at": record[4],
                }

            return None

    #insert or update ingestion record
    def upsert_ingestion_record(self, ingestion_id: str, document_id: str | None, client_id: str | None, status: str, stage: str, error: str | None = None) -> None:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO ingestions (ingestion_id, document_id, client_id, status, stage, error, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ingestion_id) DO UPDATE SET
                    document_id = excluded.document_id,
                    client_id = excluded.client_id,
                    status = excluded.status,
                    stage = excluded.stage,
                    error = excluded.error,
                    updated_at = excluded.updated_at
                """,
                (ingestion_id, document_id, client_id, status, stage, error, now, now),
            )

            conn.commit()

    #gets ingestion record
    def get_ingestion_record(self, ingestion_id: str) -> dict | None:
        with sqlite3.connect(self.db_path) as conn:    
            cursor = conn.execute(
                """
                SELECT ingestion_id, document_id, client_id, status, stage, error, created_at, updated_at
                FROM ingestions
                WHERE ingestion_id = ?
                """,
                (ingestion_id),
            )

            row = cursor.fetchone()

            if row is None:
                return None

            return dict(row)

    def get_inprogress_ingestions(self, client_id: str) -> list[dict] | None:
                
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            cursor = conn.execute(
                """
                SELECT ingestion_id, document_id, client_id, status, stage, error, created_at, updated_at
                FROM ingestions
                WHERE client_id = ?
                AND status = 'in-progress'
                ORDER BY created_at ASC
                """,
                (client_id,),
            )

            rows = cursor.fetchall()

            return [dict(row) for row in rows] if rows else []
