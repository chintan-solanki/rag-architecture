'''
This class wraps the watchdog library to provide a "stable file" watcher feature.
The standard watchdog library emits 'oncreated' event followed by several 'onmodified' events 
when a file is copied to the directory being watched. So there is no direct way to know when the file is copied completely.
This class provides a higher-level abstraction that allows registering a callback that is invoked 
once a file becomes stable. We determine a file to be stable when its size remains unchanged 
and non-zero for a specified number of consecutive checks. It uses threading to perform the checks in the background, 
so the callback is invoked from one of StableWatcher's worker threads.
'''

from __future__ import annotations

import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.polling import PollingObserver


'''
Watchdog handler.
when on_created is called, simply call submit on the stablewatcher.
'''
class WatchdogHandler(FileSystemEventHandler):
    
    def __init__(self, watcher):
        print("WatchdogHandler initialized")
        self.watcher = watcher

    def on_any_event(self, event):
        #print("Event detected: %s", event)
        pass

    def on_created(self, event):
        print("File created: %s", event.src_path)
        if event.is_directory:
            return

        # new file detected, submit to the stablewatcher for stability checking
        self.watcher.submit(Path(event.src_path))


'''
Watches a directory and invokes 'on_stable' for files that are stable.

A file is considered stable after its size remains unchanged and non-zero
for 'stable_checks' number of consecutive checks, with 'check_interval' seconds
between checks.

It also checks the existing files when the watcher starts.
It invokes the callback from one of StableWatcher's worker threads (once it determines the file is stable).
'''
class StableWatcher:
    
    def __init__(
        self,
        directory: Path,
        on_stable: Callable[[Path], None],

        stable_checks = 3,
        check_interval = 1.0,
        initial_delay = 1.0,
        max_workers = 4,
    ):
     
        self.directory = Path(directory)
        self.on_stable = on_stable
        self.stable_checks = stable_checks
        self.check_interval = check_interval
        self.initial_delay = initial_delay

        #initialize the thread pool executor 
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="stable-checker",
        )

        #instatiate watchdog observer 
        #self._observer = Observer()
        self._observer = PollingObserver(timeout=2.0) 

        self._pending: set[Path] = set() #stores a set of files that are currently being checked for stability
        self._lock = threading.Lock() #lock to coordinate access to the _pending set across multiple threads
        
        self._started = False

    #starts directory watching and stability checking. 
    def start(self):
        if self._started:
            return

        self.directory.mkdir(parents=True, exist_ok=True) #create the directory if doesn't exist

        print('directory is: ', self.directory)
        # Start Watchdog before scanning existing files.. 
        handler = WatchdogHandler(self)
        self._observer.schedule(
            handler,
            path=str(self.directory),
            recursive=False,
        )
        self._observer.start()
        self._started = True

        # Process existing files in the directory
        for path in self.directory.iterdir():
            if path.is_file():
                print('file found:',path)
                self.submit(path)
        print('existing files submitted for stability checking')

    #stops directory watching and stability checking.
    def stop(self):
        if not self._started:
            return

        self._observer.stop()
        self._observer.join()
        self._executor.shutdown(wait=True)
        self._started = False

    # add the request to pending set and schedule the stability check on a worker thread
    def submit(self, path):
        print('submit called for path:', path)
        path = path.resolve()

        with self._lock:
            if path in self._pending:
                return
            self._pending.add(path)

        future = self._executor.submit(self.wait_until_stable, path)
        future.add_done_callback(lambda _: self.mark_complete(path))

    #clean up the entry from pending set
    def mark_complete(self, path):
        with self._lock:
            self._pending.discard(path)

    #runs synchronously on a worker thread, and checks the file size at regular intervals until it is stable. 
    def wait_until_stable(self, path):
        try:
            if self.initial_delay:
                time.sleep(self.initial_delay)

            previous_size= -1
            stable_count = 0

            while True:
                try:
                    #if the file is deleted or moved, we stop checking for stability
                    if not path.is_file(): 
                        return

                    current_size = path.stat().st_size
                except FileNotFoundError:
                    return

                if current_size > 0 and current_size == previous_size:
                    stable_count += 1
                else:
                    stable_count = 0

                if stable_count >= self.stable_checks:
                    #file size ha not changed for 'stable_checks' number of checks, so it is deemed stable.
                    self.on_stable(path) #call app handler
                    return

                previous_size = current_size
                time.sleep(self.check_interval)

        except Exception:
            
            import traceback
            traceback.print_exc()

            print("Error while checking stability for %s", path)