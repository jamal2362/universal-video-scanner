# Copyright (c) 2026 Jamal2367
# Licensed under the MIT License. See LICENSE file in the project root for full license information.
"""
Media File Watcher Module
Handles file system monitoring for automatic video scanning
"""
import os
import time
import json
import threading
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import config

# Maximum time to wait for a new file to finish copying (seconds)
FILE_STABLE_TIMEOUT = 3600


class MediaFileHandler(FileSystemEventHandler):
    """Handle file system events for automatic scanning"""

    def __init__(self, scan_video_file_func, scanned_files, scanned_paths, scan_lock,
                 save_database_func, delete_cached_poster_func, deletion_event_queue=None):
        self.scan_video_file_func = scan_video_file_func
        self.scanned_files = scanned_files
        self.scanned_paths = scanned_paths
        self.scan_lock = scan_lock
        self.save_database_func = save_database_func
        self.delete_cached_poster_func = delete_cached_poster_func
        self.deletion_event_queue = deletion_event_queue

    def _notify_deletion(self, payload):
        """Send a deletion/update event to SSE clients"""
        if self.deletion_event_queue is not None:
            try:
                self.deletion_event_queue.put(json.dumps(payload))
            except Exception as e:
                print(f"Error queuing deletion event: {e}")

    def _wait_for_file_stable(self, file_path):
        """
        Wait until the file size stops changing so large files that are
        still being copied are not scanned half-written.
        Returns True once stable, False if the file disappeared or timed out.
        """
        last_size = -1
        deadline = time.time() + FILE_STABLE_TIMEOUT
        while time.time() < deadline:
            try:
                size = os.path.getsize(file_path)
            except OSError:
                return False
            if size == last_size and size > 0:
                return True
            last_size = size
            time.sleep(config.FILE_WRITE_DELAY)
        return False

    def _wait_and_scan(self, file_path):
        """Wait for the file to finish writing, then scan it"""
        if not self._wait_for_file_stable(file_path):
            print(f"File disappeared or never stabilized: {file_path}")
            return
        try:
            self.scan_video_file_func(file_path)
        except Exception as e:
            print(f"Error scanning new file {file_path}: {e}")

    def on_created(self, event):
        if event.is_directory:
            return

        file_path = event.src_path
        ext = os.path.splitext(file_path)[1].lower()

        if ext in config.SUPPORTED_FORMATS:
            print(f"New file detected: {file_path}")
            # Wait and scan in a separate thread so the watchdog event
            # thread is not blocked while large files are being copied
            threading.Thread(
                target=self._wait_and_scan,
                args=(file_path,),
                daemon=True
            ).start()

    def on_moved(self, event):
        """Handle file moves/renames - keep database in sync"""
        if event.is_directory:
            return

        src_path = event.src_path
        dest_path = event.dest_path
        src_ext = os.path.splitext(src_path)[1].lower()
        dest_ext = os.path.splitext(dest_path)[1].lower()

        if src_ext not in config.SUPPORTED_FORMATS and dest_ext not in config.SUPPORTED_FORMATS:
            return

        print(f"File move detected: {src_path} -> {dest_path}")

        rescan_needed = False
        with self.scan_lock:
            file_info = self.scanned_files.pop(src_path, None)
            self.scanned_paths.discard(src_path)

            if (file_info is not None and dest_ext in config.SUPPORTED_FORMATS
                    and os.path.basename(src_path) == os.path.basename(dest_path)):
                # Same filename, new location: keep all metadata
                file_info['path'] = dest_path
                self.scanned_files[dest_path] = file_info
                self.scanned_paths.add(dest_path)
                self.save_database_func()
                print(f"✓ Updated database path: {dest_path}")
                self._notify_deletion({'file_path': src_path})
                return

            if file_info is not None:
                if dest_ext in config.SUPPORTED_FORMATS:
                    # Renamed: metadata may no longer match, rescan below
                    rescan_needed = True
                else:
                    # Moved to an unsupported extension: treat as deletion
                    self.delete_cached_poster_func(file_info)
                    print(f"✗ Removed from database: {src_path}")
                self.save_database_func()
                self._notify_deletion({'file_path': src_path})
            elif dest_ext in config.SUPPORTED_FORMATS:
                # Unknown file moved in: scan it
                rescan_needed = True

        if rescan_needed:
            try:
                self.scan_video_file_func(dest_path)
            except Exception as e:
                print(f"Error scanning moved file {dest_path}: {e}")

    def on_deleted(self, event):
        """Handle file deletion - remove from database"""
        if event.is_directory:
            return

        file_path = event.src_path
        ext = os.path.splitext(file_path)[1].lower()

        if ext in config.SUPPORTED_FORMATS:
            print(f"File deletion detected: {file_path}")
            with self.scan_lock:
                if file_path in self.scanned_files:
                    file_info = self.scanned_files[file_path]

                    # Delete cached poster if it exists
                    self.delete_cached_poster_func(file_info)

                    del self.scanned_files[file_path]
                    self.scanned_paths.discard(file_path)
                    self.save_database_func()
                    print(f"✗ Removed from database: {file_path}")

                    # Notify SSE clients about the deletion
                    self._notify_deletion({'file_path': file_path})


def start_file_observer(scan_video_file_func, scanned_files, scanned_paths, scan_lock,
                        save_database_func, delete_cached_poster_func, deletion_event_queue=None):
    """Start watchdog observer for automatic file scanning"""
    if not os.path.exists(config.MEDIA_PATH):
        print(f"Creating media directory: {config.MEDIA_PATH}")
        os.makedirs(config.MEDIA_PATH, exist_ok=True)

    event_handler = MediaFileHandler(scan_video_file_func, scanned_files, scanned_paths,
                                     scan_lock, save_database_func, delete_cached_poster_func,
                                     deletion_event_queue)
    observer = Observer()
    observer.schedule(event_handler, config.MEDIA_PATH, recursive=True)
    observer.start()
    print(f"File observer started for: {config.MEDIA_PATH}")
    return observer
