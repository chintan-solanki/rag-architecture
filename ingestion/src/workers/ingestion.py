from bisect import bisect_left, bisect_right
from pathlib import Path
import sys
import os
from dotenv import load_dotenv
import time
from contextlib import contextmanager

@contextmanager
def timer(label):
    start = time.perf_counter()
    try:
        yield
    finally:
        end = time.perf_counter()
        print(f"{label}: {end - start:.6f} seconds")

#load environment variables from .env file
load_dotenv()

#add ingestion directory to sys.path so we can import modules from it
SRC_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = SRC_DIR.parent.parent
MODEL_DIR = ROOT_DIR / '.models'

print(f'ROOT_DIR = {ROOT_DIR}, SRC_DIR={SRC_DIR}')

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from helpers.hasher import DocumentHasher
from helpers.pdfparser import PdfParser, MarkdownSection
from helpers.indexer import Indexer, IndexDocument, IndexChunk

from common.helpers.ingestionstate import IngestionDocumentState
from common.helpers.configservice import load_config
from common.helpers.kafkahelper import KafkaHelper
from common.helpers.dbrepository import DocumentRepository
from common.helpers.redishelper import RedisHelper

print('ingestion worker up...')

#load app specific config 
config = load_config('ingestion/config/config.yml')

DOCUMENT_FETCHED_TOPI = config['kafka']['document_fetched_topic']

INGESTION_CONSUMER_GROUP = config['ingestion']['consumer_group']
QDRANT_COLLECTION = config['qdrant']['collection']
FAST_EMBEDDING_MODEL = config['qdrant']['fast_embedding_model']
EMBEDDING_MODEL_CACHE_DIR = MODEL_DIR / 'embeddings'

QDRANT_URL = os.getenv('QDRANT_URL')

hasher = DocumentHasher()
document_repository = DocumentRepository()

pdf_parser = PdfParser()
indexer = Indexer(
    qdrant_url=QDRANT_URL, 
    collection_name=QDRANT_COLLECTION, 
    fast_embedding_name=FAST_EMBEDDING_MODEL,
    embedding_cache_dir=str(EMBEDDING_MODEL_CACHE_DIR)
    )

kafkahelper = KafkaHelper()
kafkaconsumer = kafkahelper.getconsumer(DOCUMENT_FETCHED_TOPI, INGESTION_CONSUMER_GROUP, auto_offset_reset="earliest", enable_auto_commit=False)

def kafka_commit():
    try:
        kafkaconsumer.commit()
    except BaseException as excp:
        print('error committing message')

'''
This function enriches the chunk with the following citation data
    1. start and end character indexes of the chunk in the original pdf file character stream (not the section document stream)
    2. start and end page number of the chunk in the original pdf file
'''
def enrich_chunk_with_citation_data(chunk: IndexChunk, metadata: dict, page_offsets: list) -> IndexChunk:

    if chunk and metadata:
        section_start_idx = metadata['section_start_char_idx'] 

        chunk_start_idx = section_start_idx + chunk.start_char_idx
        chunk_end_idx = chunk_start_idx + len(chunk.text) 
    
        chunk_start_page_idx = bisect_right(page_offsets, chunk_start_idx) - 1
        chunk_end_page_idx = bisect_left(page_offsets, chunk_end_idx) - 1

        #set citation data in the chunk object
        chunk.start_char_idx = chunk_start_idx
        chunk.end_char_idx = chunk_end_idx
        chunk.start_page_idx = chunk_start_page_idx
        chunk.end_page_idx = chunk_end_page_idx

    return chunk 

with RedisHelper() as redis_helper:

    #process message from kafka 'document.fetched' topic
    for message in kafkaconsumer:

        message_value = message.value

        dest_file_path = message_value.get("dest_file_path")
        ingestion_id = message_value.get("ingestion_id")
        document_id = message_value.get("document_id")
        client_id = message_value.get("client_id")

        ingestion_document_state = IngestionDocumentState(document_repository, redis_helper, ingestion_id, document_id, client_id)

        print(f'message found from kafka.. document_id:{document_id}, doc_path:{dest_file_path}')

        #check if the file exists at the document path, if not log and continue to next message
        if not dest_file_path or not (file_path := Path(dest_file_path)).exists():
            print(f"Document ID: {document_id}, doc Path: {dest_file_path} does not exist.")
            kafka_commit() #kakfka ack here to avoid reprocessing this message
            continue

        #compute doc hash and check if it already exists in the database.
        file_hash = hasher.hash_document(file_path)

        if file_hash and (existing_file := document_repository.find_by_hash(file_hash)):
            print(f"Document ID: {document_id}, File Hash: {file_hash} already exists in the database with id {existing_file['document_id']}. Skipping ingestion.")
            ingestion_document_state.RecordState('failed', 'duplicate', f'document already exists {existing_file["document_id"]}')
            kafka_commit() #kakfka ack here to skip this message
            
            continue

        with timer('create pdf sections...'):
            try:
                # get list of sections from the pdf file. We then treat each section as a separate document and index it.
                file_metadata, page_offsets, sections = pdf_parser.parse(dest_file_path)
                for section in sections:
                    section.metadata.document_id = document_id
            except BaseException as exc:

                ingestion_document_state.RecordState('failed', 'parsing error', f'{exc}')
                continue

        ingestion_document_state.RecordState('in-progress', f'document parsed into sections')
        
        with timer('index chunks...'):

            try:
                print('creating index docs..')
                #create index documents from the sections and index them in the vector store.
                index_docs = [IndexDocument(
                    #doc_id is combination of file hash and section text hash
                    doc_id = f'{file_hash}_{hasher.hash_document(section.text.encode())}',
                    text=section.text,
                    metadata=section.metadata,
                ) for section in sections if isinstance(section, MarkdownSection)]

                print('calling index method..')                                            
                #indexer chunks the documents and indexes them in the vector store.
                indexer.index(
                    index_docs, 
                    transform_chunk_fn=lambda c, m: enrich_chunk_with_citation_data(c, m, page_offsets),
                    )

                print('indexing complete..')
                
            except BaseException as exc:
                print(f'indexing error {exc}')
                ingestion_document_state.RecordState('failed', 'indexing/chunking error', f'{exc}')
                continue

        ingestion_document_state.RecordState('completed', f'document successfully indexed into vector store.')

        with timer('add to database...'):
            #add the document to the database
            document_repository.insert_or_ignore(
                document_id,
                content_hash=file_hash,
                content_length=file_metadata.get('file_length', 0),
                metadata=file_metadata
            )

        print(f"Document ID: {document_id} object has been stored in db")

        with timer('kafka ack...'):
            #send kafka ack
            kafka_commit()    


print('ingestion worker finished...')
