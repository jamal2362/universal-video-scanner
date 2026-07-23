# Copyright (c) 2026 Jamal2367
# Licensed under the MIT License. See LICENSE file in the project root for full license information.
"""
Database operations module for managing scanned files
"""
import os
import json
import tempfile
import threading

# Global data storage
scanned_files = {}
scanned_paths = set()
# Reentrant so save_database() can take a consistent snapshot under the lock
# even when a caller already holds it (e.g. the scanner, the watcher and
# cleanup_database all save while mutating under this same lock).
scan_lock = threading.RLock()


def load_database(db_file):
    """Load previously scanned files from database"""
    global scanned_files, scanned_paths
    try:
        if os.path.exists(db_file):
            with open(db_file, 'r') as f:
                data = json.load(f)
                scanned_files = data.get('files', {})
                scanned_paths = set(data.get('paths', []))
                print(f"Loaded {len(scanned_files)} files from database")
    except Exception as e:
        print(f"Error loading database: {e}")
        scanned_files = {}
        scanned_paths = set()


def save_database(db_file):
    """
    Save scanned files to database atomically.

    The JSON is serialized under ``scan_lock`` (so it is a consistent snapshot
    even while other threads are scanning), then written to a temp file in the
    same directory and swapped into place with ``os.replace``. That way an
    interrupted write - container killed mid-scan, disk full - can never leave a
    half-written / corrupt database behind; the previous good copy stays intact.
    The slow disk I/O happens outside the lock so concurrent scans are not
    blocked while writing.
    """
    try:
        with scan_lock:
            payload = json.dumps({
                'files': scanned_files,
                'paths': list(scanned_paths)
            }, indent=2)
    except Exception as e:
        print(f"Error serializing database: {e}")
        return

    tmp_path = None
    try:
        dir_name = os.path.dirname(db_file) or '.'
        fd, tmp_path = tempfile.mkstemp(
            dir=dir_name, prefix='.scanned_files_', suffix='.tmp')
        with os.fdopen(fd, 'w') as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, db_file)
        tmp_path = None
    except Exception as e:
        print(f"Error saving database: {e}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def cleanup_database(db_file, delete_cached_poster_func):
    """Remove entries from database for files that no longer exist"""
    removed_count = 0
    paths_to_remove = []

    # Get list of paths to check (with lock)
    with scan_lock:
        paths_to_check = list(scanned_files.keys())

    # Check which files no longer exist (outside lock to avoid blocking)
    for file_path in paths_to_check:
        if not os.path.exists(file_path):
            paths_to_remove.append(file_path)

    # Remove non-existent files from database (with lock)
    if paths_to_remove:
        with scan_lock:
            for file_path in paths_to_remove:
                if file_path in scanned_files:  # Check if still exists in case another thread already removed it
                    file_info = scanned_files[file_path]

                    # Delete cached poster if it exists
                    delete_cached_poster_func(file_info)

                    del scanned_files[file_path]
                    scanned_paths.discard(file_path)
                    removed_count += 1
                    print(
                        f"✗ Removed from database (file not found): {file_path}")

            if removed_count > 0:
                save_database(db_file)

    return removed_count
