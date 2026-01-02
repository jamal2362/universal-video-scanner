"""
Media File Watcher Module
Handles file system monitoring for automatic video scanning
"""
import os
import time
import json
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import config

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

    def on_created(self, event):
        if event.is_directory:
            return

        file_path = event.src_path
        ext = os.path.splitext(file_path)[1].lower()

        if ext in config.SUPPORTED_FORMATS:
            print(f"New file detected: {file_path}")
            time.sleep(config.FILE_WRITE_DELAY)
            try:
                self.scan_video_file_func(file_path)
            except Exception as e:
                print(f"Error scanning new file {file_path}: {e}")

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
                    if self.deletion_event_queue is not None:
                        try:
                            self.deletion_event_queue.put(json.dumps({'file_path': file_path}))
                        except Exception as e:
                            print(f"Error queuing deletion event: {e}")


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

