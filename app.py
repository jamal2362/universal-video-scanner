#!/usr/bin/env python3
"""
Universal Video Scanner - Main Application
Flask web application for scanning and managing video files
"""
import os
import re
import threading
import queue
from flask import Flask, render_template, jsonify, request, send_file, Response

# Import configuration
import config

# Import utility functions
from utils.file_utils import cleanup_temp_directory
from utils.i18n import translate, get_request_language

# Import service modules
from services import database
from services.tmdb_service import get_tmdb_poster, get_tmdb_poster_by_id, get_tmdb_credits
from services.fanart_service import get_fanart_poster
from services.poster_service import delete_cached_poster, get_cached_backdrop_path, migrate_poster_urls_to_cache
from services.video_scanner import scan_video_file, scan_directory, background_scan_new_files

# Import watcher
from watchers.media_watcher import start_file_observer

# Initialize Flask app
app = Flask(__name__,
            template_folder=config.TEMPLATES_DIR,
            static_folder=config.STATIC_DIR)

# Event queue for Server-Sent Events
deletion_event_queue = queue.Queue()


# Helper function wrappers to pass dependencies to scan_video_file
def _scan_video_file_wrapper(file_path):
    """Wrapper function for scan_video_file with all dependencies"""
    return scan_video_file(
        file_path,
        database.scanned_paths,
        database.scanned_files,
        database.scan_lock,
        lambda: database.save_database(config.DB_FILE),
        lambda filename: get_fanart_poster(filename, config.FANART_API_KEY, config.CONTENT_LANGUAGE),
        lambda filename: get_tmdb_poster(filename, config.TMDB_API_KEY, config.CONTENT_LANGUAGE),
        lambda tmdb_id, media_type: get_tmdb_poster_by_id(tmdb_id, media_type, config.TMDB_API_KEY, config.CONTENT_LANGUAGE),
        lambda tmdb_id, media_type: get_tmdb_credits(tmdb_id, media_type, config.TMDB_API_KEY),
        lambda tmdb_id, poster_url: get_cached_backdrop_path(tmdb_id, poster_url, config.POSTER_CACHE_DIR)
    )


def _delete_cached_poster_wrapper(file_info):
    """Wrapper function for delete_cached_poster with dependencies"""
    return delete_cached_poster(file_info, config.POSTER_CACHE_DIR)


# Flask Routes

@app.route('/')
def index():
    """Main page showing scanned files"""
    files_list = list(database.scanned_files.values())
    # Sort by filename
    files_list.sort(key=lambda x: x['filename'])

    return render_template(
        'index.html',
        files=files_list,
        file_count=len(files_list),
        auto_refresh_interval=config.AUTO_REFRESH_INTERVAL)


@app.route('/scan', methods=['POST'])
def manual_scan():
    """Endpoint for manual scan trigger"""
    try:
        # Clean up database for non-existent files
        removed_count = database.cleanup_database(config.DB_FILE, _delete_cached_poster_wrapper)

        # Scan for new files
        new_files = scan_directory(config.MEDIA_PATH, database.scanned_paths)

        # Scan each new file
        scanned_new_count = 0
        for file_path in new_files:
            try:
                result = _scan_video_file_wrapper(file_path)
                if result and result.get('success', False):
                    scanned_new_count += 1
            except Exception as e:
                print(f"Error scanning {file_path}: {e}")

        final_count = len(database.scanned_files)

        return jsonify({
            'success': True,
            'new_files': scanned_new_count,
            'removed_files': removed_count,
            'total_files': final_count
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/get_files', methods=['GET'])
def get_files():
    """Get list of available video files for dropdown selection"""
    try:
        all_files = []
        for root, dirs, files in os.walk(config.MEDIA_PATH):
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in config.SUPPORTED_FORMATS:
                    file_path = os.path.join(root, file)
                    is_scanned = file_path in database.scanned_paths
                    all_files.append({
                        'path': file_path,
                        'name': file,  # Only filename, not path
                        'scanned': is_scanned
                    })

        # Sort by name (A-Z, case-insensitive)
        all_files.sort(key=lambda x: x['name'].lower())

        return jsonify({
            'success': True,
            'files': all_files
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/scan_file', methods=['POST'])
def scan_single_file():
    """Endpoint to scan a specific file"""
    try:
        # Get user's preferred language
        lang = get_request_language(request)

        data = request.get_json()
        file_path = data.get('file_path')

        if not file_path:
            return jsonify({
                'success': False,
                'error': translate('api_no_file_path_provided', lang)
            }), 400

        if not os.path.exists(file_path):
            return jsonify({
                'success': False,
                'error': translate('api_file_not_found', lang)
            }), 404

        # Scan the file
        result = _scan_video_file_wrapper(file_path)

        if result:
            return jsonify({
                'success': True,
                'message': translate('api_file_scanned_successfully', lang),
                'file_info': result
            })
        else:
            return jsonify({
                'success': False,
                'message': translate('api_file_not_profile_or_scanned', lang)
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/poster/<filename>')
def serve_poster(filename):
    """Serve cached poster images"""
    try:
        # Validate filename to prevent path traversal attacks
        # Only allow alphanumeric, underscore, hyphen, and .jpg extension
        if not re.match(r'^[a-zA-Z0-9_-]+\.jpg$', filename):
            print(f"Invalid poster filename: {filename}")
            return "Invalid filename", 400

        # Prevent directory traversal
        if '..' in filename or '/' in filename or '\\' in filename:
            print(f"Path traversal attempt detected: {filename}")
            return "Invalid filename", 400

        backdrop_path = os.path.join(config.POSTER_CACHE_DIR, filename)

        # Verify the resolved path is still within POSTER_CACHE_DIR
        if not os.path.abspath(backdrop_path).startswith(
                os.path.abspath(config.POSTER_CACHE_DIR)):
            print(f"Path traversal attempt detected: {filename}")
            return "Invalid filename", 400

        if os.path.exists(backdrop_path):
            return send_file(backdrop_path, mimetype='image/jpeg')
        else:
            return "Poster not found", 404
    except Exception as e:
        print(f"Error serving poster {filename}: {e}")
        return "Error serving poster", 500


@app.route('/events')
def events():
    """Server-Sent Events endpoint for real-time updates"""
    def event_stream():
        # Send a keep-alive comment every 30 seconds
        import time
        last_keepalive = time.time()

        while True:
            try:
                # Check for deletion events (non-blocking with timeout)
                try:
                    event_data = deletion_event_queue.get(timeout=1)
                    yield f"event: file_deleted\ndata: {event_data}\n\n"
                except queue.Empty:
                    # Send keep-alive every 30 seconds
                    current_time = time.time()
                    if current_time - last_keepalive > 30:
                        yield ": keep-alive\n\n"
                        last_keepalive = current_time
            except GeneratorExit:
                break

    return Response(event_stream(), mimetype='text/event-stream')


def main():
    """Main application entry point"""
    print("=" * 50)
    print("Starting Universal Video Scanner")
    print("=" * 50)

    # Ensure all required directories exist
    config.ensure_directories()

    # Clean up any orphaned temporary files from previous runs
    cleanup_temp_directory(config.TEMP_DIR)

    # Load existing database
    database.load_database(config.DB_FILE)

    # Show configured content language
    print(f"Content language: {config.CONTENT_LANGUAGE.upper()}")

    # Migrate existing poster URLs to cached versions
    if config.REQUESTS_AVAILABLE:
        print(f"Image source: {config.IMAGE_SOURCE.upper()}")
        if config.IMAGE_SOURCE == 'fanart':
            if config.FANART_API_KEY:
                print("✓ Fanart.tv API key configured")
            else:
                print("⚠ Warning: Fanart.tv selected but FANART_API_KEY not configured - no posters will be fetched")
        elif config.IMAGE_SOURCE == 'tmdb':
            if config.TMDB_API_KEY:
                print("✓ TMDB API key configured")
            else:
                print("⚠ Warning: TMDB selected but TMDB_API_KEY not configured - no posters will be fetched")
        else:
            print(f"⚠ Warning: Unknown IMAGE_SOURCE '{config.IMAGE_SOURCE}' - defaulting to TMDB")
            if config.TMDB_API_KEY:
                print("✓ TMDB API key configured")
            else:
                print("⚠ Warning: TMDB_API_KEY not configured - no posters will be fetched")
        print("Migrating poster URLs to cache...")
        migrate_poster_urls_to_cache(
            database.scanned_files,
            database.scan_lock,
            lambda: database.save_database(config.DB_FILE),
            config.POSTER_CACHE_DIR
        )

    # Clean up database for non-existent files
    removed_count = database.cleanup_database(config.DB_FILE, _delete_cached_poster_wrapper)
    if removed_count > 0:
        print(f"Cleaned up {removed_count} entries for non-existent files")

    # Start file observer in background
    observer = start_file_observer(
        _scan_video_file_wrapper,
        database.scanned_files,
        database.scanned_paths,
        database.scan_lock,
        lambda: database.save_database(config.DB_FILE),
        _delete_cached_poster_wrapper,
        deletion_event_queue
    )

    # Start initial scan automatically in background
    threading.Thread(
        target=background_scan_new_files,
        args=(database.scanned_paths, _scan_video_file_wrapper),
        daemon=True
    ).start()
    print("Initial scan started...")

    # Start Flask app
    try:
        app.run(host='0.0.0.0', port=2367, debug=False)
    except KeyboardInterrupt:
        print("Shutting down...")
        observer.stop()
        observer.join()
        # Clean up temp directory on shutdown
        cleanup_temp_directory(config.TEMP_DIR)


if __name__ == '__main__':
    main()
