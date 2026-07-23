# Copyright (c) 2026 Jamal2367
# Licensed under the MIT License. See LICENSE file in the project root for full license information.
"""
Configuration module for Universal Video Scanner
Contains all environment variables, constants, and configuration settings
"""
import os

# Check if requests module is available
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    print("Warning: 'requests' module not available. TMDB integration disabled.")

# Environment Variables and Base Paths
MEDIA_PATH = '/media'
DATA_DIR = '/app/data'
DB_FILE = os.path.join(DATA_DIR, 'scanned_files.json')
POSTER_CACHE_DIR = os.path.join(DATA_DIR, 'posters')

# API Keys and Configuration
TMDB_API_KEY = os.environ.get('TMDB_API_KEY', '')
FANART_API_KEY = os.environ.get('FANART_API_KEY', '')
IMAGE_SOURCE = os.environ.get('IMAGE_SOURCE', 'tmdb').lower()
CONTENT_LANGUAGE = os.environ.get('CONTENT_LANGUAGE', 'en').lower()

# Language code mapping from ISO 639-1 to various formats used by MediaInfo
LANGUAGE_CODE_MAP = {
    'en': ['eng', 'en', 'english'],
    'de': ['ger', 'deu', 'de', 'german'],
    'ru': ['rus', 'ru', 'russian'],
    'bg': ['bul', 'bg', 'bulgarian'],
    'fr': ['fre', 'fra', 'fr', 'french'],
    'es': ['spa', 'es', 'spanish'],
    'it': ['ita', 'it', 'italian'],
    'pt': ['por', 'pt', 'portuguese'],
    'ja': ['jpn', 'ja', 'japanese'],
    'ko': ['kor', 'ko', 'korean'],
    'zh': ['chi', 'zho', 'zh', 'chinese'],
    'nl': ['dut', 'nld', 'nl', 'dutch'],
    'pl': ['pol', 'pl', 'polish'],
    'sv': ['swe', 'sv', 'swedish'],
    'no': ['nor', 'no', 'norwegian'],
    'da': ['dan', 'da', 'danish'],
    'fi': ['fin', 'fi', 'finnish'],
    'tr': ['tur', 'tr', 'turkish'],
    'ar': ['ara', 'ar', 'arabic'],
    'he': ['heb', 'he', 'hebrew'],
    'hi': ['hin', 'hi', 'hindi'],
    'th': ['tha', 'th', 'thai'],
    'cs': ['cze', 'ces', 'cs', 'czech'],
    'hu': ['hun', 'hu', 'hungarian'],
    'ro': ['rum', 'ron', 'ro', 'romanian'],
    'el': ['gre', 'ell', 'el', 'greek'],
    'uk': ['ukr', 'uk', 'ukrainian'],
}

# Static files configuration
# Use bundled static files from /app directory instead of downloading from GitHub
TEMPLATES_DIR = '/app/templates'
STATIC_DIR = '/app/static'
CSS_DIR = os.path.join(STATIC_DIR, 'css')
JS_DIR = os.path.join(STATIC_DIR, 'js')
LOCALE_DIR = os.path.join(STATIC_DIR, 'locale')
FONTS_DIR = os.path.join(STATIC_DIR, 'fonts')


def get_templates_dir():
    """
    Get the templates directory path.
    Prefers the copy in DATA_DIR if it exists, otherwise uses the bundled version.
    """
    data_templates = os.path.join(DATA_DIR, 'templates')
    if os.path.exists(data_templates):
        return data_templates
    return TEMPLATES_DIR


def get_static_dir():
    """
    Get the static directory path.
    Prefers the copy in DATA_DIR if it exists, otherwise uses the bundled version.
    """
    data_static = os.path.join(DATA_DIR, 'static')
    if os.path.exists(data_static):
        return data_static
    return STATIC_DIR

# Scanner configuration constants
FILE_WRITE_DELAY = int(os.environ.get('FILE_WRITE_DELAY', '5'))
AUTO_REFRESH_INTERVAL = int(os.environ.get('AUTO_REFRESH_INTERVAL', '10'))

# Number of files probed at once during a bulk scan (initial + manual scan).
# hdrprobe and MediaInfo run as external processes, so a small worker pool
# overlaps their I/O and cuts the total time to scan a large library.
# Default 1 keeps the scan strictly sequential and light on resources - the
# safest choice for a single spinning disk / NAS, where parallel reads cause
# seek thrashing that is slower, not faster. Raise it (e.g. 2-4) only for SSD /
# NVMe / fast network storage where concurrent reads pay off.
SCAN_WORKERS = max(1, int(os.environ.get('SCAN_WORKERS', '1')))

# During a bulk scan the database is persisted every this many newly scanned
# files instead of after every single file. Rewriting the whole JSON after each
# file is O(n^2) disk I/O on a large library; batching keeps the scan fast and
# light while still bounding progress loss: an interrupted scan re-reads at most
# this many files next time. Set to 1 to persist after every file (old behavior).
SCAN_SAVE_BATCH = max(1, int(os.environ.get('SCAN_SAVE_BATCH', '25')))

# Size (in MB) of the main-feature .m2ts sample extracted from a Blu-ray disc
# image (.iso) for MediaInfo analysis. MediaInfo only needs the stream headers
# at the start of the clip, so a small prefix identifies every track reliably
# without reading the whole (multi-gigabyte) file - keeping the scan fast and
# light. Point TMPDIR at a tmpfs (e.g. /dev/shm) to keep the sample in RAM and
# avoid disk writes entirely. Raise this only if a disc fails to be detected.
ISO_SAMPLE_SIZE_MB = int(os.environ.get('ISO_SAMPLE_SIZE_MB', '16'))

# Bitrate estimation constant for format-level fallback
# When only format-level bitrate is available, estimate audio as 10% of total
AUDIO_BITRATE_FORMAT_ESTIMATE_RATIO = 0.1

# Supported video formats
# .iso disc images and .m2ts streams are analyzed via hdrprobe, which reads
# a disc's playlists and automatically picks the main feature (the largest
# main-movie .m2ts) for reporting.
SUPPORTED_FORMATS = {'.mkv', '.mp4', '.m4v', '.ts', '.m2ts', '.hevc', '.iso'}


def ensure_directories():
    """Ensure all required directories exist. Call this from main() in app.py"""
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(POSTER_CACHE_DIR, exist_ok=True)
