from common.helpers.dbrepository import DocumentRepository
from common.helpers.redishelper import RedisHelper
from typing import Any

class IngestionDocumentState():

    def __init__(self, document_repository: DocumentRepository, redis_helper: RedisHelper, ingestion_id:str, document_id:str, client_id:str):
        self.document_repository = document_repository
        self.redis_helper = redis_helper
        self.ingestion_id = ingestion_id
        self.document_id = document_id
        self.client_id = client_id

        self.redis_channel = f'{self.client_id}_ingestion'

        if not ingestion_id or not document_id or not client_id:
            raise ValueError('ingestion_id, document_id, and client_id must be provided')

    def RecordState(self, status:str, stage:str, error:str = ''):

        print(f'Record state: {self.client_id}, {self.ingestion_id}, {status} | {stage}')

        try:
            #upsert ingestion record in db
            self.document_repository.upsert_ingestion_record(self.ingestion_id, self.document_id, self.client_id, status, stage, error)
        except Exception as exc:
            print(f'error updating ingestion record in db {exc}')
            return

        #publish to redis client_id channel    
        if self.redis_helper:
            try:    
                self.redis_helper.publish(self.redis_channel, {
                    'ingestion_id': self.ingestion_id,
                    'document_id' : self.document_id,
                    'client_id': self.client_id,
                    'status': status,
                    'stage': stage,
                    'error': error
                })

            except Exception as exc:
                print(f'error publishing to redis: {exc}')



