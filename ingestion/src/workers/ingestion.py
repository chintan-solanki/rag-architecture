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

print(f'ROOT_DIR = {ROOT_DIR}, SRC_DIR={SRC_DIR}')

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from helpers.hasher import DocumentHasher
from helpers.dbrepository import FileRepository
from helpers.pdfparser import PdfParser, MarkdownSection, SectionMetadata
from helpers.indexer import Indexer, IndexDocument, IndexChunk
from helpers.kafkahelper import KafkaHelper
from helpers.configservice import load_config
from kafka import KafkaConsumer

print('ingestion worker up...')

#load app specific config 
config = load_config()['ingestion']
KAFKA_SUBSCRIBE_TOPIC = config['kafka_subscribe_topic']
KAFKA_SUBSCRIBE_CONSUMER_GROUP = config['kafka_subscribe_consumer_group']
QDRANT_COLLECTION = config['qdrant_collection']
FAST_EMBEDDING_MODEL = config['fast_embedding_model']

#load env config
DB_PATH = str(ROOT_DIR / os.getenv('DB_REL_PATH'))
QDRANT_URL = os.getenv('QDRANT_URL')

hasher = DocumentHasher()
file_repository = FileRepository(db_path=DB_PATH)
pdf_parser = PdfParser()
indexer = Indexer(qdrant_url=QDRANT_URL, collection_name=QDRANT_COLLECTION, fast_embedding_name=FAST_EMBEDDING_MODEL)

kafkahelper = KafkaHelper()
kafka_consumer = kafkahelper.getconsumer(KAFKA_SUBSCRIBE_TOPIC, KAFKA_SUBSCRIBE_CONSUMER_GROUP)

def kafka_commit():
    try:
        kafka_consumer.commit()
    except Exception as excp:
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

for message in kafka_consumer:

    message_value = message.value

    file_id = message_value.get("file_id")
    source_path = message_value.get("source_path")

    print(f'message found from kafka.. file_id:{file_id}, source_path:{source_path}')

    #check if the file exists at the source path, if not log and continue to next message
    if not source_path or not (file_path := Path(source_path)).exists():
        print(f"File ID: {file_id}, Source Path: {source_path} does not exist.")
        kafka_commit() #kakfka ack here to avoid reprocessing this message
        continue

    #compute doc hash and check if it already exists in the database.
    file_hash = hasher.hash_document(file_path)
    print(f'File ID: {file_id}, Source Path: {source_path} has hash {file_hash}')

    if file_hash and (existing_file := file_repository.find_by_hash(file_hash)):
        print(f"File ID: {file_id}, File Hash: {file_hash} already exists in the database with id {existing_file['file_id']}. Skipping ingestion.")
        kafka_commit() #kakfka ack here to skip this message
        continue
    else:
        print(existing_file)

    with timer('create pdf sections...'):
        # get list of sections from the pdf file. We then treat each section as a separate document and index it.
        file_metadata, page_offsets, sections = pdf_parser.parse(source_path)
        print(f"File ID: {file_id}, Source Path: {source_path} has been parsed into {len(sections)} sections.")

    with timer('index chunks...'):
        #create index documents from the sections and index them in the vector store.
        
        index_docs = [IndexDocument(
            #doc_id is combination of file hash and section text hash
            doc_id = f'{file_hash}_{hasher.hash_document(section.text.encode())}',
            text=section.text,
            metadata=section.metadata,
        ) for section in sections if isinstance(section, MarkdownSection)]
                                                                                
        #indexer chunks the documents and indexes them in the vector store.
        index = indexer.index(
            index_docs, 
            transform_chunk_fn=lambda c, m: enrich_chunk_with_citation_data(c, m, page_offsets),
            )

    print(f"File ID: {file_id}, Source Path: {source_path} has been indexed")

    with timer('add to database...'):
        #add the document to the database
        file_repository.insert_or_ignore(
            file_id=file_id,
            content_hash=file_hash,
            content_length=file_metadata.get('file_length', 0),
            metadata=file_metadata
        )

    print(f"File ID: {file_id} object has been stored in db")

    with timer('kafka ack...'):
        #send kafka ack
        kafka_commit()    
    

print('ingestion worker finished...')
