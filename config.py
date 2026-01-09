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
TEMP_DIR = '/app/temp'
DB_FILE = os.path.join(DATA_DIR, 'scanned_files.json')
POSTER_CACHE_DIR = os.path.join(DATA_DIR, 'posters')

# API Keys and Configuration
TMDB_API_KEY = os.environ.get('TMDB_API_KEY', '')
FANART_API_KEY = os.environ.get('FANART_API_KEY', '')
IMAGE_SOURCE = os.environ.get('IMAGE_SOURCE', 'tmdb').lower()
CONTENT_LANGUAGE = os.environ.get('CONTENT_LANGUAGE', 'en').lower()

# Language code mapping from ISO 639-1 to various formats used by MediaInfo/ffprobe
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

# Bitrate estimation constant for format-level fallback
# When only format-level bitrate is available, estimate audio as 10% of total
AUDIO_BITRATE_FORMAT_ESTIMATE_RATIO = 0.1

# Supported video formats
SUPPORTED_FORMATS = {'.mkv', '.mp4', '.m4v', '.ts', '.hevc'}


def ensure_directories():
    """Ensure all required directories exist. Call this from main() in app.py"""
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(TEMP_DIR, exist_ok=True)
    os.makedirs(POSTER_CACHE_DIR, exist_ok=True)
