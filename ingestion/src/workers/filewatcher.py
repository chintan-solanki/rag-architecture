from __future__ import annotations

import re
import shutil
import uuid
from pathlib import Path
import sys
import time

#add ingestion directory to sys.path so we can import modules from it
SRC_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = SRC_DIR.parent.parent

print(f'ROOT_DIR = {ROOT_DIR}, SRC_DIR={SRC_DIR}')

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from common.helpers.configservice import load_config
from helpers.stablewatcher import StableWatcher

from common.helpers.kafkahelper import KafkaHelper
from common.helpers.dbrepository import DocumentRepository

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

config = load_config('ingestion/config/config.yml')

INCOMING_DIR = Path(config['staging']['incoming_dir_path'])
FETCHED_DIR = Path(config['staging']['fetched_dir_path'])
STABLE_CHECKS = config['filewatcher']['stable_checks']
CHECK_INTERVAL = config['filewatcher']['check_interval']
INITIAL_DELAY = config['filewatcher']['initial_delay']
MAX_WORKERS = config['filewatcher']['max_workers']
DOCUMENT_FETCHED_TOPIC = config['kafka']['document_fetched_topic']

kafkahelper = KafkaHelper()
document_repository = DocumentRepository()

DOCUMENT_ID_PREFIX = re.compile(r"^(?P<ingestion_id>[0-9a-fA-F]{32})_.*")

def publish_kafka_event(ingestion_id, document_id, client_id, destination):
    event = {
        "ingestion_id": ingestion_id,
        "document_id": document_id,
        "client_id": client_id,

        "source_type": "filewatcher",
        "dest_file_path": str(destination),
        "dest_file_name": destination.name,
        "dest_file_type": destination.suffix,
    }
    
    kafkahelper.send_event(DOCUMENT_FETCHED_TOPIC, event)

def handle_stable_file(source: Path) -> None:
    
    if not source.exists():
        print("Stable file disappeared before processing: %s", source)
        return

    FETCHED_DIR.mkdir(parents=True, exist_ok=True)

    client_id = ''

    # check if the file is already in already contains the ingestion_id
    match = DOCUMENT_ID_PREFIX.match(source.stem)
    if match:
        #file came from the api, so file stem is the document_id. use the same file name as the target.
        ingestion_id, document_id = match.group("ingestion_id"), match.group(0)
        dest_name = source.name

        #retrieve client_id from ingestion record.
        ingestion_record = document_repository.get_ingestion_record(ingestion_id)

        if ingestion_record and ingestion_record.client_id:
            client_id = ingestion_record.client_id

    else:
        #the file was copied in incoming directory manually

        #generate a random ingestion id
        ingestion_id = uuid.uuid4().hex

        #generate document id by combining ingestion id and source file stem
        document_id = f'{ingestion_id}_{source.stem}'

        client_id = 'filewatcher'
        
        #dest name is document_id and file  suffix
        dest_name = f'{document_id}.{source.suffix}'

    destination = FETCHED_DIR / dest_name
    
    copied, ignored = False, False

    #copy from incoming to fetched directory
    try:
        if not source.suffix == '.Identifier': #skip copying zone identifier files (wsl)
            print("Copying %s -> %s", source, destination)
            shutil.copy2(source, destination)
            copied = True
        else:
            ignored = True
    except Exception:
        print("Failed to copy %s", source)
        return

    #publish kafka event for the copied file if it was copied and not ignored
    if not ignored and copied:

        try:
            #update ingestion record in db
            document_repository.upsert_ingestion_record(ingestion_id, document_id, client_id, 'in-progress', 'document.fetched')
        except Exception as exc:
            print(f"Failed to update ingestion record for {ingestion_id}")
            print(exc)
            return 
        
        try:
            #publish kafka event for the copied file
            publish_kafka_event(ingestion_id, document_id, client_id, destination)
        except Exception:
            print("Failed to publish kafka event for %s", destination)
            return

    #delete the source file after copying or if it was ignored (e.g., zone identifier files)
    if ignored or copied:
        try:
            source.unlink() 
        except Exception:
            print(
                "Failed to delete source %s",
                source,
            )
            return

# -----------------------------------------------------------------------------
# Application lifecycle
# -----------------------------------------------------------------------------

def main() -> None:
    watcher = StableWatcher(
        INCOMING_DIR,
        handle_stable_file,
        stable_checks=STABLE_CHECKS,
        check_interval=CHECK_INTERVAL,
        initial_delay=INITIAL_DELAY,
        max_workers=MAX_WORKERS,
    )

    watcher.start()

    try:
        # Watcher owns its own background threads. Keep this application
        # process alive until interrupted.
        while True:
            # A simple synchronous service loop is sufficient for now, can be replaced
            # by a more sophisticated event loop or signal handling if needed.
            time.sleep(60)

    except KeyboardInterrupt:
        print("Shutdown requested")

    finally:
        watcher.stop()
        print("File watcher stopped")


if __name__ == "__main__":
    main()
