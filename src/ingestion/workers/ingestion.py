from bisect import bisect_left, bisect_right
from pathlib import Path
import sys
import os
from dotenv import load_dotenv

#load environment variables from .env file
load_dotenv()

#add ingestion directory to sys.path so we can import modules from it
INGESTION_DIR = Path(__file__).resolve().parent.parent

if str(INGESTION_DIR) not in sys.path:
    sys.path.insert(0, str(INGESTION_DIR))

from helpers.hasher import DocumentHasher
from helpers.dbrepository import FileRepository
from helpers.pdfparser import PdfParser, MarkdownSection, SectionMetadata
from helpers.indexer import Indexer, IndexDocument, IndexChunk

#from helpers.kafkahelper import KafkaHelper

from llama_index.core import StorageContext, VectorStoreIndex
from llama_index.core.agent.workflow import FunctionAgent
from llama_index.llms.openai import OpenAI
from llama_index.embeddings.huggingface import HuggingFaceEmbedding

print('ingestion worker up...')

hasher = DocumentHasher()
file_repository = FileRepository()
pdf_parser = PdfParser()
indexer = Indexer()

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


#kafkahelper = KafkaHelper()
#kafka_consumer = kafkahelper.getconsumer("document_fetched", "ingestion_worker_group")

messages = [{
    'file_id': 'd28e7b44d5cb422d8bd50fcdadd53358', 
    'source_type': 'filewatcher', 
    'source_path': '/app/staging/fetched/Intro_to_Literature_d28e7b44d5cb422d8bd50fcdadd53358.pdf', 
    'file_type': '.pdf'
    }] 

for message_value in messages:
    
    file_id = message_value.get("file_id")
    source_path = message_value.get("source_path")

    #check if the file exists at the source path, if not log and continue to next message
    if not source_path or not (file_path := Path(source_path)).exists():
        print(f"File ID: {file_id}, Source Path: {source_path} does not exist.")
        #todo: kakfka ack here to avoid reprocessing this message
        continue

    #compute doc hash and check if it already exists in the database.
    file_hash = hasher.hash_document(file_path)
    print(f'File ID: {file_id}, Source Path: {source_path} has hash {file_hash}')

    if file_hash and (existing_file := file_repository.find_by_hash(file_hash)):
        print(f"File ID: {file_id}, File Hash: {file_hash} already exists in the database with id {existing_file['file_id']}. Skipping ingestion.")
        #todo: kakfka ack here to avoid reprocessing this message   
        continue

    # get list of sections from the pdf file. We then treat each section as a separate document and index it.
    file_metadata, page_offsets, sections = pdf_parser.parse(source_path)
    print(f"File ID: {file_id}, Source Path: {source_path} has been parsed into {len(sections)} sections.")

    #create index documents from the sections and index them in the vector store.
    index_docs = [IndexDocument(
        text=section.text,
        metadata=section.metadata,
    ) for section in sections if isinstance(section, MarkdownSection)]

                                                                               
    #indexer chunks the documents and indexes them in the vector store.
    index = indexer.index(
        index_docs, 
        transform_chunk_fn=lambda c, m: enrich_chunk_with_citation_data(c, m, page_offsets)
        )

    print(f"File ID: {file_id}, Source Path: {source_path} has been indexed")

    #add the document to the database
    file_repository.insert_or_ignore(
        file_id=file_id,
        content_hash=file_hash,
        content_length=file_metadata.get('file_length', 0),
        metadata=file_metadata
    )
    

print('ingestion worker finished...')
