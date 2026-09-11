from __future__ import annotations

import json
import logging
import os
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

from helpers.configservice import load_config
from helpers.stablewatcher import StableWatcher
from helpers.kafkahelper import KafkaHelper

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

config = load_config()['filewatcher']

INCOMING_DIR = ROOT_DIR / config['incoming_dir_rel_path']
FETCHED_DIR = ROOT_DIR / config['fetched_dir_rel_path']
STABLE_CHECKS = config['stable_checks']
CHECK_INTERVAL = config['check_interval']
INITIAL_DELAY = config['initial_delay']
MAX_WORKERS = config['max_workers']

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

kafka_helper = KafkaHelper()

def make_unique_destination(source: Path) -> Path:
    
    destination = FETCHED_DIR / source.name

    if not destination.exists():
        return destination

    return (
        FETCHED_DIR
        / f"{source.stem}_{uuid.uuid4().hex}{source.suffix}"
    )

def publish_kafka_event(file_path, file_id):
    event = {
        "file_id": file_id,
        "source_type": "filewatcher",
        "source_path": str(file_path),
        "file_type": file_path.suffix,
    }
    
    kafka_helper.send_event("document_fetched", event)

def handle_stable_file(source: Path) -> None:
    
    if not source.exists():
        print("Stable file disappeared before processing: %s", source)
        return

    FETCHED_DIR.mkdir(parents=True, exist_ok=True)

    #create a unique file id for the file
    file_id = str(uuid.uuid4().hex)

    #destination = make_unique_destination(source)
    destination = FETCHED_DIR / f"{source.stem}_{file_id}{source.suffix}"

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
            #publish kafka event for the copied file
            publish_kafka_event(destination, file_id)
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

