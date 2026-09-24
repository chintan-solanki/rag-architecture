import json
import sqlite3

class FileRepository:
    def __init__(self, db_path):
        print(f'db_path = {db_path}')

        self.db_path = db_path
        self.create_schema(self.db_path)

    def create_schema(self, db_path):
        with sqlite3.connect(db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS files (
                    document_id TEXT PRIMARY KEY,
                    content_hash TEXT NOT NULL UNIQUE,
                    content_length INTEGER NOT NULL,
                    
                    metadata TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

    def find_by_hash(self, content_hash):
        record = None
        with sqlite3.connect(self.db_path) as conn:
            record = conn.execute(
                """
                SELECT document_id, content_length
                FROM files
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

    def insert_or_ignore(self, document_id, content_hash, content_length, metadata={}):

        record = None

        metadata_str = json.dumps(metadata) if metadata else '{}' 

        with sqlite3.connect(self.db_path) as conn:
            
            record = conn.execute(
                """
                INSERT OR IGNORE INTO files
                    (document_id, content_hash, content_length, metadata)
                VALUES (?, ?, ?, ?)
                RETURNING document_id;
                """,
                (document_id, content_hash, content_length, metadata_str),
            ).fetchone()
        
        if record:
            return record[0]

        return None

    def get_file(self, document_id):

        record = None
        with sqlite3.connect(self.db_path) as conn:
            record = conn.execute(
                """
                SELECT document_id, content_hash, content_length, metadata, created_at
                FROM files
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