#!/usr/bin/env python3
import os
import json
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.request
import re
import hashlib
from pathlib import Path
from urllib.parse import urlparse
from flask import Flask, render_template, jsonify, request, send_file
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    print("Warning: 'requests' module not available. TMDB integration disabled.")

# Configuration
MEDIA_PATH = '/media'
DATA_DIR = '/app/data'
TEMP_DIR = '/app/temp'
DB_FILE = os.path.join(DATA_DIR, 'scanned_files.json')
POSTER_CACHE_DIR = os.path.join(DATA_DIR, 'posters')
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

# Compiled regex patterns for better performance
TMDB_ID_PATTERN = re.compile(r'\{tmdb-(\d+)\}', re.IGNORECASE)
YEAR_PATTERN = re.compile(r'\b(19|20)\d{2}\b')
RESOLUTION_PATTERN = re.compile(r'\b(480|720|1080|2160)[pi]\b', re.IGNORECASE)
CODEC_PATTERN = re.compile(r'\b(x264|x265|h264|h265|hevc)\b', re.IGNORECASE)
SOURCE_PATTERN = re.compile(
    r'\b(BluRay|BRRip|WEBRip|WEB-DL|HDRip|DVDRip)\b',
    re.IGNORECASE)
HDR_PATTERN = re.compile(
    r'\b(DV|HDR10\+?|HLG|SDR|Dolby[\.\s]?Vision)\b',
    re.IGNORECASE)
BRACKET_PATTERN = re.compile(r'[\[\(].*?[\]\)]')
SEPARATOR_PATTERN = re.compile(r'[._\-]')
WHITESPACE_PATTERN = re.compile(r'\s+')

# Static files configuration
TEMPLATES_DIR = os.path.join(DATA_DIR, 'templates')
STATIC_DIR = os.path.join(DATA_DIR, 'static')
CSS_DIR = os.path.join(STATIC_DIR, 'css')
JS_DIR = os.path.join(STATIC_DIR, 'js')
LOCALE_DIR = os.path.join(STATIC_DIR, 'locale')
FONTS_DIR = os.path.join(STATIC_DIR, 'fonts')

# GitHub raw URLs for downloading static files
GITHUB_RAW_BASE = 'https://raw.githubusercontent.com/U3knOwn/universal-video-scanner/main'
GITHUB_FILES = {
    'templates/index.html': os.path.join(TEMPLATES_DIR, 'index.html'),
    'static/css/style.css': os.path.join(CSS_DIR, 'style.css'),
    'static/js/main.js': os.path.join(JS_DIR, 'main.js'),
    'static/locale/de.json': os.path.join(LOCALE_DIR, 'de.json'),
    'static/locale/en.json': os.path.join(LOCALE_DIR, 'en.json'),
    'static/fonts/inter.css': os.path.join(FONTS_DIR, 'inter.css'),
    'static/fonts/Inter-Regular.woff2': os.path.join(FONTS_DIR, 'Inter-Regular.woff2'),
    'static/fonts/Inter-Medium.woff2': os.path.join(FONTS_DIR, 'Inter-Medium.woff2'),
    'static/fonts/Inter-SemiBold.woff2': os.path.join(FONTS_DIR, 'Inter-SemiBold.woff2'),
    'static/fonts/Inter-Bold.woff2': os.path.join(FONTS_DIR, 'Inter-Bold.woff2'),
    'static/favicon.ico': os.path.join(STATIC_DIR, 'favicon.ico'),
}

app = Flask(__name__,
            template_folder=TEMPLATES_DIR,
            static_folder=STATIC_DIR)

# Scanner configuration constants
FILE_WRITE_DELAY = int(os.environ.get('FILE_WRITE_DELAY', '5'))

# Bitrate estimation constant for format-level fallback
# When only format-level bitrate is available, estimate audio as 10% of total
AUDIO_BITRATE_FORMAT_ESTIMATE_RATIO = 0.1

# Supported video formats
SUPPORTED_FORMATS = {'.mkv', '.mp4', '.m4v', '.ts', '.hevc'}

# Global data storage
scanned_files = {}
scanned_paths = set()
scan_lock = threading.Lock()

# Ensure directories exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(TEMPLATES_DIR, exist_ok=True)
os.makedirs(CSS_DIR, exist_ok=True)
os.makedirs(JS_DIR, exist_ok=True)
os.makedirs(LOCALE_DIR, exist_ok=True)
os.makedirs(FONTS_DIR, exist_ok=True)
os.makedirs(POSTER_CACHE_DIR, exist_ok=True)


def download_static_files():
    """Download missing static files from GitHub"""
    missing_files = []

    # Check which files are missing
    for github_path, local_path in GITHUB_FILES.items():
        if not os.path.exists(local_path):
            missing_files.append((github_path, local_path))

    if not missing_files:
        print("✓ All static files present")
        return True

    print(f"Downloading {len(missing_files)} missing file(s) from GitHub...")

    for github_path, local_path in missing_files:
        try:
            url = f"{GITHUB_RAW_BASE}/{github_path}"
            print(f"  Downloading: {github_path}")

            # Download file
            with urllib.request.urlopen(url) as response:
                content = response.read()

            # Save file
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            with open(local_path, 'wb') as f:
                f.write(content)

            print(f"  ✓ Saved: {local_path}")
        except Exception as e:
            print(f"  ✗ Error downloading {github_path}: {e}")
            return False

    print("✓ All static files downloaded successfully")
    return True


def update_static_files():
    """Force update all static files from GitHub"""
    print("Updating all static files from GitHub...")

    for github_path, local_path in GITHUB_FILES.items():
        try:
            url = f"{GITHUB_RAW_BASE}/{github_path}"
            print(f"  Updating: {github_path}")

            # Download file
            with urllib.request.urlopen(url) as response:
                content = response.read()

            # Save file
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            with open(local_path, 'wb') as f:
                f.write(content)

            print(f"  ✓ Updated: {local_path}")
        except Exception as e:
            print(f"  ✗ Error updating {github_path}: {e}")
            return False

    print("✓ All static files updated successfully")
    return True


def cleanup_temp_directory():
    """Clean up temporary directory to prevent accumulation of orphaned files"""
    try:
        if os.path.exists(TEMP_DIR):
            for item in os.listdir(TEMP_DIR):
                item_path = os.path.join(TEMP_DIR, item)
                try:
                    if os.path.isfile(item_path) or os.path.islink(item_path):
                        os.unlink(item_path)
                    elif os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                except Exception as e:
                    print(f"Error deleting {item_path}: {e}")
            print(f"Cleaned up temp directory: {TEMP_DIR}")
    except Exception as e:
        print(f"Error cleaning temp directory: {e}")

# TMDB API Integration Functions


def extract_tmdb_id(filename):
    """Extract TMDB ID from filename - pattern: {tmdb-12345}"""
    match = TMDB_ID_PATTERN.search(filename)
    if match:
        return match.group(1)
    return None


def extract_movie_name(filename):
    """Extract movie name from filename for search fallback"""
    # Remove file extension
    name = os.path.splitext(filename)[0]

    # Remove TMDB ID pattern if present
    name = TMDB_ID_PATTERN.sub('', name)

    # Remove common patterns like year, quality, resolution, etc.
    name = YEAR_PATTERN.sub('', name)
    name = RESOLUTION_PATTERN.sub('', name)
    name = CODEC_PATTERN.sub('', name)
    name = SOURCE_PATTERN.sub('', name)
    name = HDR_PATTERN.sub('', name)
    name = BRACKET_PATTERN.sub('', name)

    # Replace common separators with spaces
    name = SEPARATOR_PATTERN.sub(' ', name)

    # Clean up multiple spaces
    name = WHITESPACE_PATTERN.sub(' ', name).strip()

    return name


def delete_cached_poster(file_info):
    """Delete cached poster file for a given file_info entry"""
    poster_url = file_info.get('poster_url', '')
    if poster_url.startswith('/poster/'):
        poster_filename = poster_url.replace('/poster/', '')
        backdrop_path = os.path.join(POSTER_CACHE_DIR, poster_filename)
        if os.path.exists(backdrop_path):
            try:
                os.remove(backdrop_path)
                print(f"✗ Removed cached poster: {poster_filename}")
            except Exception as e:
                print(f"Error removing poster {poster_filename}: {e}")


def extract_title_and_year_from_tmdb(data, media_type):
    """Extract title and year from TMDB API response data"""
    # Extract title based on media type
    if media_type == 'movie':
        title = data.get('title')
        release_date = data.get('release_date', '')
    else:  # TV show
        title = data.get('name')
        release_date = data.get('first_air_date', '')

    # Extract year (first 4 characters) from release date
    year = release_date[:4] if release_date and len(release_date) >= 4 else None
    
    return title, year


def get_tmdb_title_and_year_by_id(tmdb_id, media_type='movie'):
    """Fetch only title and year from TMDB API by ID (without poster)"""
    if not TMDB_API_KEY or not REQUESTS_AVAILABLE:
        return None, None

    # Validate tmdb_id is numeric
    if not tmdb_id or not isinstance(tmdb_id, (str, int)) or not str(tmdb_id).isdigit():
        print(f"Invalid TMDB ID: {tmdb_id}")
        return None, None

    try:
        url = f'https://api.themoviedb.org/3/{media_type}/{tmdb_id}'
        
        # Try configured language first
        params = {'api_key': TMDB_API_KEY, 'language': CONTENT_LANGUAGE}
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            title, year = extract_title_and_year_from_tmdb(data, media_type)
            if title:
                return title, year
        
        # If configured language request failed, try English fallback
        if CONTENT_LANGUAGE != 'en' and response.status_code != 200:
            params = {'api_key': TMDB_API_KEY, 'language': 'en'}
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                title, year = extract_title_and_year_from_tmdb(data, media_type)
                if title:
                    return title, year
        
        if response.status_code not in [200, 404]:
            print(f"TMDB API error for ID {tmdb_id}: HTTP {response.status_code}")
    except requests.exceptions.Timeout:
        print(f"TMDB API timeout for ID {tmdb_id}")
    except requests.exceptions.RequestException as e:
        print(f"TMDB API request error for ID {tmdb_id}: {e}")
    except Exception as e:
        print(f"Error fetching TMDB title/year by ID {tmdb_id}: {e}")

    return None, None


def get_tmdb_poster_by_id(tmdb_id, media_type='movie'):
    """Fetch poster URL, title, year, rating, and plot from TMDB API by ID"""
    if not TMDB_API_KEY or not REQUESTS_AVAILABLE:
        return None, None, None, None, None

    # Validate tmdb_id is numeric
    if not tmdb_id or not isinstance(
            tmdb_id, (str, int)) or not str(tmdb_id).isdigit():
        print(f"Invalid TMDB ID: {tmdb_id}")
        return None, None, None, None, None

    try:
        url = f'https://api.themoviedb.org/3/{media_type}/{tmdb_id}'
        
        # Try configured language first
        params = {'api_key': TMDB_API_KEY, 'language': CONTENT_LANGUAGE}
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            backdrop_path = data.get('backdrop_path')
            rating = data.get('vote_average')  # TMDB rating (0-10 scale)
            plot = data.get('overview', '')

            if backdrop_path:
                title, year = extract_title_and_year_from_tmdb(data, media_type)
                poster_url = f'https://image.tmdb.org/t/p/original{backdrop_path}'
                return poster_url, title, year, rating, plot
        
        # If configured language request failed or didn't have poster, try English fallback
        if CONTENT_LANGUAGE != 'en' and (response.status_code != 200 or not data.get('backdrop_path')):
            params = {'api_key': TMDB_API_KEY, 'language': 'en'}
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                backdrop_path = data.get('backdrop_path')
                rating = data.get('vote_average')
                plot = data.get('overview', '')
                
                if backdrop_path:
                    title, year = extract_title_and_year_from_tmdb(data, media_type)
                    poster_url = f'https://image.tmdb.org/t/p/original{backdrop_path}'
                    return poster_url, title, year, rating, plot
        
        if response.status_code not in [200, 404]:
            print(
                f"TMDB API error for ID {tmdb_id}: HTTP "
                f"{response.status_code}")
    except requests.exceptions.Timeout:
        print(f"TMDB API timeout for ID {tmdb_id}")
    except requests.exceptions.RequestException as e:
        print(f"TMDB API request error for ID {tmdb_id}: {e}")
    except Exception as e:
        print(f"Error fetching TMDB poster by ID {tmdb_id}: {e}")

    return None, None, None, None, None


def search_tmdb_poster(movie_name, media_type='movie'):
    """Search TMDB for movie/tv show and return poster URL, title, year, rating, and plot"""
    if not TMDB_API_KEY or not REQUESTS_AVAILABLE or not movie_name:
        return None, None, None, None, None

    # Validate and sanitize movie_name
    if not isinstance(movie_name, str):
        return None, None, None, None, None

    # Trim and validate length
    movie_name = movie_name.strip()
    if len(movie_name) < 1 or len(movie_name) > 200:
        print(f"Invalid movie name length: {len(movie_name)}")
        return None, None, None, None, None

    try:
        url = f'https://api.themoviedb.org/3/search/{media_type}'
        
        # Try configured language first
        params = {
            'api_key': TMDB_API_KEY,
            'query': movie_name,
            'language': CONTENT_LANGUAGE
        }

        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            results = data.get('results', [])
            if results:
                # Get first result
                first_result = results[0]
                backdrop_path = first_result.get('backdrop_path')
                rating = first_result.get('vote_average')
                plot = first_result.get('overview', '')

                if backdrop_path:
                    title, year = extract_title_and_year_from_tmdb(first_result, media_type)
                    poster_url = f'https://image.tmdb.org/t/p/original{backdrop_path}'
                    return poster_url, title, year, rating, plot
        
        # If configured language search failed or returned no results with posters, try English fallback
        if CONTENT_LANGUAGE != 'en' and (response.status_code != 200 or not results or not results[0].get('backdrop_path')):
            params = {
                'api_key': TMDB_API_KEY,
                'query': movie_name,
                'language': 'en'
            }
            
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                results = data.get('results', [])
                if results:
                    first_result = results[0]
                    backdrop_path = first_result.get('backdrop_path')
                    rating = first_result.get('vote_average')
                    plot = first_result.get('overview', '')
                    
                    if backdrop_path:
                        title, year = extract_title_and_year_from_tmdb(first_result, media_type)
                        poster_url = f'https://image.tmdb.org/t/p/original{backdrop_path}'
                        return poster_url, title, year, rating, plot
        
        if response.status_code not in [200, 404]:
            print(
                f"TMDB API search error for '{movie_name}': HTTP "
                f"{response.status_code}")
    except requests.exceptions.Timeout:
        print(f"TMDB API timeout searching for '{movie_name}'")
    except requests.exceptions.RequestException as e:
        print(f"TMDB API request error searching for '{movie_name}': {e}")
    except Exception as e:
        print(f"Error searching TMDB for '{movie_name}': {e}")

    return None, None, None, None, None


def get_tmdb_poster(filename):
    """Main function: Try ID first, then fallback to name search. Returns (tmdb_id, poster_url, title, year, rating, plot)"""
    if not TMDB_API_KEY or not REQUESTS_AVAILABLE:
        return None, None, None, None, None, None

    # Try to extract TMDB ID first
    tmdb_id = extract_tmdb_id(filename)
    if tmdb_id:
        print(f"  [TMDB] Found TMDB ID: {tmdb_id}")
        # Try movie first
        poster_url, title, year, rating, plot = get_tmdb_poster_by_id(tmdb_id, 'movie')
        if poster_url:
            print(f"  [TMDB] Poster found by ID (movie): {poster_url}")
            return tmdb_id, poster_url, title, year, rating, plot
        # Try TV show
        poster_url, title, year, rating, plot = get_tmdb_poster_by_id(tmdb_id, 'tv')
        if poster_url:
            print(f"  [TMDB] Poster found by ID (TV): {poster_url}")
            return tmdb_id, poster_url, title, year, rating, plot

    # Fallback: Search by name
    movie_name = extract_movie_name(filename)
    if movie_name:
        print(f"  [TMDB] Searching by name: '{movie_name}'")
        # Try movie search first
        poster_url, title, year, rating, plot = search_tmdb_poster(movie_name, 'movie')
        if poster_url:
            print(f"  [TMDB] Poster found by search (movie): {poster_url}")
            return None, poster_url, title, year, rating, plot
        # Try TV search
        poster_url, title, year, rating, plot = search_tmdb_poster(movie_name, 'tv')
        if poster_url:
            print(f"  [TMDB] Poster found by search (TV): {poster_url}")
            return None, poster_url, title, year, rating, plot

    print(f"  [TMDB] No poster found for: {filename}")
    return None, None, None, None, None, None


def get_tmdb_credits(tmdb_id, media_type='movie'):
    """Fetch directors and cast from TMDB API by ID. Returns (directors_list, cast_list)"""
    if not TMDB_API_KEY or not REQUESTS_AVAILABLE:
        return [], []
    
    # Validate tmdb_id is numeric
    if not tmdb_id or not isinstance(tmdb_id, (str, int)) or not str(tmdb_id).isdigit():
        print(f"Invalid TMDB ID for credits: {tmdb_id}")
        return [], []
    
    try:
        url = f'https://api.themoviedb.org/3/{media_type}/{tmdb_id}/credits'
        params = {'api_key': TMDB_API_KEY}
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            # Extract directors from crew (limit to 3)
            directors = []
            crew = data.get('crew', [])
            for member in crew:
                if member.get('job') == 'Director':
                    name = member.get('name', '').strip()
                    if name:  # Only add non-empty names
                        directors.append(name)
                        if len(directors) >= 3:
                            break
            
            # Extract cast (limit to 10)
            cast = []
            cast_list = data.get('cast', [])
            for actor in cast_list[:10]:
                name = actor.get('name', '').strip()
                if name:  # Only add non-empty names
                    cast.append(name)
            
            return directors, cast
        
        if response.status_code not in [200, 404]:
            print(f"TMDB credits API error for ID {tmdb_id}: HTTP {response.status_code}")
    except requests.exceptions.Timeout:
        print(f"TMDB credits API timeout for ID {tmdb_id}")
    except requests.exceptions.RequestException as e:
        print(f"TMDB credits API request error for ID {tmdb_id}: {e}")
    except Exception as e:
        print(f"Error fetching TMDB credits for ID {tmdb_id}: {e}")
    
    return [], []


def is_valid_tmdb_url(url):
    """Validate URL is from TMDB to prevent SSRF attacks"""
    if not url:
        return False

    try:
        parsed = urlparse(url)
        # Check scheme is https
        if parsed.scheme != 'https':
            return False
        # Check hostname is exactly image.tmdb.org (not a subdomain or similar
        # domain)
        if parsed.netloc != 'image.tmdb.org':
            return False
        # Check path starts with /t/p/
        if not parsed.path.startswith('/t/p/'):
            return False
        return True
    except Exception:
        return False


# Fanart.tv API Integration Functions


def is_valid_fanart_url(url):
    """Validate URL is from Fanart.tv to prevent SSRF attacks"""
    if not url:
        return False

    try:
        parsed = urlparse(url)
        # Check scheme is https
        if parsed.scheme != 'https':
            return False
        # Check hostname is exactly assets.fanart.tv
        if parsed.netloc != 'assets.fanart.tv':
            return False
        # Check path starts with /fanart/
        if not parsed.path.startswith('/fanart/'):
            return False
        return True
    except Exception:
        return False


def get_fanart_poster_by_id(tmdb_id, media_type='movie'):
    """Fetch thumb poster URL from Fanart.tv API by TMDB ID"""
    if not FANART_API_KEY or not REQUESTS_AVAILABLE:
        return None

    # Validate tmdb_id is a valid numeric string or integer
    if not tmdb_id or not isinstance(tmdb_id, (str, int)) or not str(tmdb_id).isdigit():
        print(f"Invalid TMDB ID for Fanart.tv: {tmdb_id}")
        return None

    try:
        if media_type == 'movie':
            url = f'https://webservice.fanart.tv/v3/movies/{tmdb_id}'
        else:  # TV show - Note: Fanart.tv uses TVDB ID for TV shows, not TMDB
            # For TV shows, we would need TVDB ID, which we don't have
            # So we'll return None for TV shows
            print(f"  [FANART] TV shows not supported (requires TVDB ID)")
            return None
        
        params = {'api_key': FANART_API_KEY}
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            # Get moviethumb for movies
            if media_type == 'movie':
                thumbs = data.get('moviethumb', [])
                if thumbs:
                    # Helper function to safely get likes
                    def get_likes(thumb):
                        try:
                            return int(thumb.get('likes', 0))
                        except (ValueError, TypeError):
                            return 0
                    
                    # Filter by preferred language first
                    preferred_thumbs = [t for t in thumbs if t.get('lang', '').lower() == CONTENT_LANGUAGE]
                    if preferred_thumbs:
                        preferred_thumbs_sorted = sorted(preferred_thumbs, key=get_likes, reverse=True)
                        thumb_url = preferred_thumbs_sorted[0].get('url')
                        if thumb_url:
                            print(f"  [FANART] Thumb poster found in {CONTENT_LANGUAGE}: {thumb_url}")
                            return thumb_url
                    
                    # Fallback to English if no images in preferred language
                    if CONTENT_LANGUAGE != 'en':
                        en_thumbs = [t for t in thumbs if t.get('lang', '').lower() == 'en']
                        if en_thumbs:
                            en_thumbs_sorted = sorted(en_thumbs, key=get_likes, reverse=True)
                            thumb_url = en_thumbs_sorted[0].get('url')
                            if thumb_url:
                                print(f"  [FANART] Thumb poster found in en (fallback): {thumb_url}")
                                return thumb_url
                    
                    # Final fallback: all images sorted by likes
                    thumbs_sorted = sorted(thumbs, key=get_likes, reverse=True)
                    thumb_url = thumbs_sorted[0].get('url')
                    if thumb_url:
                        print(f"  [FANART] Thumb poster found (any language): {thumb_url}")
                        return thumb_url
        
        if response.status_code not in [200, 404]:
            print(
                f"Fanart.tv API error for ID {tmdb_id}: HTTP "
                f"{response.status_code}")
    except requests.exceptions.Timeout:
        print(f"Fanart.tv API timeout for ID {tmdb_id}")
    except requests.exceptions.RequestException as e:
        print(f"Fanart.tv API request error for ID {tmdb_id}: {e}")
    except Exception as e:
        print(f"Error fetching Fanart.tv poster by ID {tmdb_id}: {e}")

    return None


def get_fanart_poster(filename):
    """Main function for Fanart.tv: Try ID first. Returns (tmdb_id, poster_url)"""
    if not FANART_API_KEY or not REQUESTS_AVAILABLE:
        return None, None

    # Try to extract TMDB ID first (Fanart.tv requires TMDB ID)
    tmdb_id = extract_tmdb_id(filename)
    if tmdb_id:
        print(f"  [FANART] Found TMDB ID: {tmdb_id}")
        # Try movie first
        poster_url = get_fanart_poster_by_id(tmdb_id, 'movie')
        if poster_url:
            print(f"  [FANART] Poster found by ID (movie): {poster_url}")
            return tmdb_id, poster_url
        # Note: TV shows would need TVDB ID, which we don't extract

    print(f"  [FANART] No poster found for: {filename}")
    return None, None


def download_and_cache_poster(poster_url, cache_filename):
    """Download poster image and cache it locally"""
    if not poster_url:
        return None

    # Validate URL is from TMDB or Fanart.tv to prevent SSRF attacks
    if not is_valid_tmdb_url(poster_url) and not is_valid_fanart_url(poster_url):
        print(f"  [CACHE] Invalid poster URL (not from TMDB or Fanart.tv): {poster_url}")
        return poster_url

    cache_path = os.path.join(POSTER_CACHE_DIR, cache_filename)

    # Check if already cached
    if os.path.exists(cache_path):
        print(f"  [CACHE] Poster already cached: {cache_filename}")
        return f'/poster/{cache_filename}'

    try:
        print(f"  [CACHE] Downloading poster: {poster_url}")
        response = requests.get(poster_url, timeout=10)
        if response.status_code == 200:
            # Save to cache
            with open(cache_path, 'wb') as f:
                f.write(response.content)
            print(f"  [CACHE] Poster cached: {cache_filename}")
            return f'/poster/{cache_filename}'
    except requests.exceptions.Timeout:
        print(f"  [CACHE] Timeout downloading poster")
    except requests.exceptions.RequestException as e:
        print(f"  [CACHE] Error downloading poster: {e}")
    except Exception as e:
        print(f"  [CACHE] Unexpected error caching poster: {e}")

    # Return original URL as fallback
    return poster_url


def get_cached_backdrop_path(tmdb_id, poster_url):
    """Get cached poster path or download and cache it"""
    if not poster_url:
        return None

    # Generate cache filename based on source and TMDB ID or URL hash
    if tmdb_id:
        # Determine source from URL validation
        if is_valid_fanart_url(poster_url):
            cache_filename = f"fanart_{tmdb_id}.jpg"
        elif is_valid_tmdb_url(poster_url):
            cache_filename = f"tmdb_{tmdb_id}.jpg"
        else:
            # Fallback to hash-based naming for unknown sources
            url_hash = hashlib.md5(poster_url.encode()).hexdigest()
            cache_filename = f"poster_{url_hash}.jpg"
    else:
        # Extract filename from URL using hash
        url_hash = hashlib.md5(poster_url.encode()).hexdigest()
        cache_filename = f"poster_{url_hash}.jpg"

    return download_and_cache_poster(poster_url, cache_filename)


def load_database():
    """Load previously scanned files from database"""
    global scanned_files, scanned_paths
    try:
        if os.path.exists(DB_FILE):
            with open(DB_FILE, 'r') as f:
                data = json.load(f)
                scanned_files = data.get('files', {})
                scanned_paths = set(data.get('paths', []))
                print(f"Loaded {len(scanned_files)} files from database")
    except Exception as e:
        print(f"Error loading database: {e}")
        scanned_files = {}
        scanned_paths = set()


def migrate_poster_urls_to_cache():
    """Migrate existing TMDB and Fanart.tv poster URLs to cached versions"""
    global scanned_files

    if not REQUESTS_AVAILABLE:
        return

    migrated_count = 0
    with scan_lock:
        for file_path, file_info in scanned_files.items():
            poster_url = file_info.get('poster_url')
            tmdb_id = file_info.get('tmdb_id')

            # Check if poster URL is a TMDB or Fanart.tv URL (not cached)
            if poster_url and (is_valid_tmdb_url(poster_url) or is_valid_fanart_url(poster_url)):
                print(
                    f"  [MIGRATION] Caching poster for: "
                    f"{file_info.get('filename')}")
                cached_path = get_cached_backdrop_path(tmdb_id, poster_url)
                if cached_path and cached_path.startswith('/poster/'):
                    file_info['poster_url'] = cached_path
                    migrated_count += 1

        if migrated_count > 0:
            save_database()
            print(f"✓ Migrated {migrated_count} poster(s) to cache")


def save_database():
    """Save scanned files to database"""
    try:
        with open(DB_FILE, 'w') as f:
            json.dump({
                'files': scanned_files,
                'paths': list(scanned_paths)
            }, f, indent=2)
    except Exception as e:
        print(f"Error saving database: {e}")


def cleanup_database():
    """Remove entries from database for files that no longer exist"""
    global scanned_files, scanned_paths

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
                    delete_cached_poster(file_info)
                    
                    del scanned_files[file_path]
                    scanned_paths.discard(file_path)
                    removed_count += 1
                    print(
                        f"✗ Removed from database (file not found): {file_path}")

            if removed_count > 0:
                save_database()

    return removed_count


def extract_dovi_metadata(video_file):
    """
    Extract Dolby Vision metadata using ffmpeg pipe + dovi_tool JSON output
    Returns dict with profile + el_type or None
    """
    rpu_path = None
    ffmpeg_proc = None

    try:
        # Extract first second of video
        ffmpeg_cmd = [
            'ffmpeg',
            '-i', video_file,
            '-map', '0:v:0',
            '-c:v', 'copy',
            '-to', '1',
            '-f', 'hevc',
            '-'
        ]

        ffmpeg_proc = subprocess.Popen(
            ffmpeg_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL
        )

        # Create temp file for RPU data
        with tempfile.NamedTemporaryFile(dir=TEMP_DIR, suffix='.bin', delete=False) as rpu_tmp:
            rpu_path = rpu_tmp.name

        # Extract RPU metadata
        dovi_extract = subprocess.run(
            ['dovi_tool', 'extract-rpu', '-', '-o', rpu_path],
            stdin=ffmpeg_proc.stdout,
            capture_output=True,
            timeout=30
        )

        # Wait for ffmpeg to complete
        if ffmpeg_proc:
            ffmpeg_proc.wait(timeout=30)

        # Check if RPU file was created and has content
        if not os.path.exists(rpu_path):
            print(
                f"  [DV] No RPU file created for "
                f"{os.path.basename(video_file)}")
            return None

        if os.path.getsize(rpu_path) == 0:
            print(f"  [DV] Empty RPU file for {os.path.basename(video_file)}")
            return None

        # Get Dolby Vision info from RPU
        dovi_info = subprocess.run(
            ['dovi_tool', 'info', '-i', rpu_path, '-f', '0'],
            capture_output=True,
            timeout=30
        )

        if dovi_info.returncode != 0:
            stderr = dovi_info.stderr.decode('utf-8', errors='ignore')
            print(
                f"  [DV] dovi_tool info failed for "
                f"{os.path.basename(video_file)}: {stderr}")
            return None

        # Parse output
        output = dovi_info.stdout.decode('utf-8')

        # The output format is: first line is summary, rest is JSON
        lines = output.strip().split('\n')
        if len(lines) < 2:
            print(
                f"  [DV] Unexpected dovi_tool output format for "
                f"{os.path.basename(video_file)}")
            return None

        json_data = '\n'.join(lines[1:])
        metadata = json.loads(json_data)

        profile = metadata.get('dovi_profile')
        el_type = metadata.get('el_type', '').upper()

        print(
            f"  [DV] Dolby Vision detected: Profile {profile}, EL Type: "
            f"{el_type or 'None'}")

        return {
            'profile': profile,
            'el_type': el_type if el_type else ''
        }

    except subprocess.TimeoutExpired as e:
        print(f"  [DV] Timeout while extracting Dolby Vision metadata: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"  [DV] Failed to parse dovi_tool JSON output: {e}")
        return None
    except Exception as e:
        print(
            f"  [DV] Dolby Vision extraction error for "
            f"{os.path.basename(video_file)}: {e}")
        return None
    finally:
        # Clean up temp file
        try:
            if rpu_path and os.path.exists(rpu_path):
                os.remove(rpu_path)
        except Exception as e:
            print(f"  [DV] Failed to remove temp file {rpu_path}: {e}")

        # Ensure ffmpeg process is terminated
        try:
            if ffmpeg_proc and ffmpeg_proc.poll() is None:
                ffmpeg_proc.terminate()
                ffmpeg_proc.wait(timeout=5)
        except Exception:
            pass


def detect_hdr_format(video_file):
    """
    Detect HDR format: SDR, HDR10, HDR10+, HLG, Dolby Vision (FEL/MEL)
    Returns dict with 'format', 'detail', and optionally 'profile'/'el_type'
    """
    try:
        print(f"[HDR] Analyzing: {os.path.basename(video_file)}")

        # --- Step 1: Dolby Vision ---
        dovi = extract_dovi_metadata(video_file)
        if dovi:
            profile = dovi.get('profile')
            el_type = dovi.get('el_type', '').upper()
            detail = f'DV Profile {profile}'
            print(f"  -> Dolby Vision {detail}")
            return {
                'format': 'Dolby Vision',
                'profile': profile,
                'el_type': el_type,
                'detail': detail
            }

        # --- Step 2: HDR10+ (dynamic metadata) ---
        try:
            mi_cmd = ['mediainfo', '--Output=JSON', video_file]
            mi_proc = subprocess.run(mi_cmd, capture_output=True, text=True, timeout=10)
            if mi_proc.returncode == 0 and mi_proc.stdout:
                try:
                    mi_json = json.loads(mi_proc.stdout)
                    media = mi_json.get('media', {}) or {}
                    tracks = media.get('track', []) or []
                    # find video tracks (MediaInfo uses @type == "Video")
                    for t in tracks:
                        ttype = (t.get('@type') or '').lower()
                        if ttype != 'video':
                            continue
                        hdr_format = (t.get('HDR_Format') or '') or (t.get('HDR format') or '')
                        hdr_compat = (t.get('HDR_Format_Compatibility') or '') or (t.get('HDR format compatibility') or '')
                        lf = (hdr_format or '').lower()
                        lc = (hdr_compat or '').lower()

                        # 1) Direct HDR10+ mentions (strong signal)
                        if 'hdr10+' in lf or 'hdr10plus' in lf or 'hdr10+' in lc or 'hdr10plus' in lc:
                            print(f"  -> HDR10+ detected (MediaInfo explicit): HDR_Format='{hdr_format}' HDR_Format_Compatibility='{hdr_compat}'")
                            return {
                                'format': 'HDR10+',
                                'detail': 'HDR10+',
                                'profile': 'HDR10+',
                                'el_type': ''
                            }

                        # 2) SMPTE ST 2094 / App 4 detection (must be 2094, NOT 2084)
                        # Require explicit '2094' or 'app 4' or 'smpte st 2094' to avoid matching PQ (2084).
                        if (('2094' in lf or 'app 4' in lf or 'app4' in lf or 'smpte st 2094' in lf or 'smpte2094' in lf)
                                and '2084' not in lf):
                            print(f"  -> HDR10+ detected (MediaInfo SMPTE ST 2094 / App 4): HDR_Format='{hdr_format}'")
                            return {
                                'format': 'HDR10+',
                                'detail': 'HDR10+',
                                'profile': 'HDR10+',
                                'el_type': ''
                            }

                        # 3) Compatibility field mentioning HDR10+ or profile A (explicit compatibility)
                        if any(k in lc for k in ['hdr10+ profile', 'profile a', 'hdr10+']):
                            print(f"  -> HDR10+ detected (MediaInfo compatibility): HDR_Format_Compatibility='{hdr_compat}'")
                            return {
                                'format': 'HDR10+',
                                'detail': 'HDR10+',
                                'profile': 'HDR10+',
                                'el_type': ''
                            }
                except Exception as e:
                    print(f"  [HDR] Failed parsing MediaInfo JSON: {e}")
        except FileNotFoundError:
            # mediainfo not installed / not available in PATH
            pass
        except Exception as e:
            print(f"  [HDR] MediaInfo call failed: {e}")

        # Fallback: Full stream info text search (existing logic) - stricter pattern
        cmd = [
            'ffprobe', '-v', 'error',
            '-select_streams', 'v:0',
            '-show_streams',
            video_file
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=15)
        except Exception as e:
            result = None
            print(f"  [HDR] ffprobe show_streams call failed: {e}")

        if result and result.returncode == 0:
            output_lower = (result.stdout or '').lower()
            # only match explicit HDR10+ or explicit SMPTE ST 2094 mentions (not generic 'smpte')
            if any(indicator in output_lower for indicator in [
                    'hdr10+',
                    'hdr10plus',
                    'smpte st 2094',
                    'smpte2094',
                    'smpte-st-2094']):
                print(f"  -> HDR10+ detected (fallback text search)")
                return {
                    'format': 'HDR10+',
                    'detail': 'HDR10+',
                    'profile': 'HDR10+',
                    'el_type': ''
                }

        # --- Step 3: HDR10 / HLG (static metadata) ---
        cmd = [
            'ffprobe', '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=color_transfer,color_primaries',
            '-of', 'json',
            video_file
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=15)
        except Exception as e:
            result = None
            print(f"  [HDR] ffprobe color metadata call failed: {e}")

        if result and result.returncode == 0:
            try:
                data = json.loads(result.stdout)
                streams = data.get('streams', [])
                if streams:
                    st = streams[0]
                    transfer = (st.get('color_transfer') or '').lower()
                    primaries = (st.get('color_primaries') or '').lower()
                    # HLG detection
                    if 'hlg' in transfer or 'arib' in transfer:
                        print("  -> HLG detected")
                        return {'format': 'HLG', 'detail': 'HLG', 'profile': '', 'el_type': ''}
                    # PQ / HDR10 detection (SMPTE ST 2084 / PQ)
                    if any(x in transfer for x in ['pq', 'smpte2084', 'smpte st 2084', 'smpte-st-2084']):
                        print("  -> PQ transfer detected (likely HDR10)")
                        return {'format': 'HDR10', 'detail': 'HDR10', 'profile': '', 'el_type': ''}
                    # If BT.2020 primaries present -> assume HDR10
                    if 'bt2020' in primaries or 'bt.2020' in primaries:
                        print("  -> BT.2020 primaries detected (likely HDR10)")
                        return {'format': 'HDR10', 'detail': 'HDR10', 'profile': '', 'el_type': ''}
            except Exception as e:
                print(f"  [HDR] color metadata parsing failed: {e}")

        # Final fallback: SDR
        print("  -> No HDR metadata found: assuming SDR")
        return {'format': 'SDR', 'detail': 'SDR', 'profile': '', 'el_type': ''}

    except Exception as e:
        print(f"  [HDR] Unexpected error while detecting HDR format: {e}")
        return {'format': 'Unknown', 'detail': 'Error', 'profile': '', 'el_type': ''}


def get_video_resolution(video_file):
    """Get video resolution using ffprobe and return friendly name"""
    try:
        cmd = [
            'ffprobe', '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height',
            '-of', 'json',
            video_file
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10)
        if result.returncode == 0:
            data = json.loads(result.stdout)
            if 'streams' in data and len(data['streams']) > 0:
                stream = data['streams'][0]
                width = stream.get('width', 0)
                height = stream.get('height', 0)

                # Map resolution to friendly names
                if width == 3840 and height == 2160:
                    return "4K (UHD)"
                elif width == 1920 and height == 1080:
                    return "1080p (Full HD)"
                elif width == 1280 and height == 720:
                    return "720p (HD)"
                elif width == 7680 and height == 4320:
                    return "8K (UHD)"
                elif width == 2560 and height == 1440:
                    return "1440p"
                elif width == 4096 and height == 2160:
                    return "4K DCI"
                elif width == 1366 and height == 768:
                    return "768p"
                elif width == 854 and height == 480:
                    return "480p (SD)"
                elif width == 640 and height == 480:
                    return "480p (SD)"
                else:
                    return f"{width}x{height}"
    except Exception as e:
        print(f"Error getting resolution: {e}")
    return "Unknown"


def get_channel_format(channels):
    """Convert channel count to standard format string"""
    try:
        channels = int(channels)
        channel_map = {
            1: "1.0",
            2: "2.0",
            3: "2.1",
            4: "3.1",
            5: "4.1",
            6: "5.1",
            7: "6.1",
            8: "7.1",
            9: "8.1",
            10: "9.1"
        }
        return channel_map.get(channels, f"{channels}.0")
    except (ValueError, TypeError):
        return ""


def get_audio_info_mediainfo(video_file):
    """Get audio information using MediaInfo"""
    try:
        cmd = ['mediainfo', '--Output=JSON', video_file]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10)
        if result.returncode == 0:
            data = json.loads(result.stdout)
            if data.get('media') and 'track' in data['media']:
                audio_tracks = [track for track in data['media']
                                ['track'] if track.get('@type') == 'Audio']
                if audio_tracks:
                    return audio_tracks
    except Exception as e:
        print(f"Error getting audio info from MediaInfo: {e}")
    return None


def get_video_duration(video_file):
    """Get video duration in seconds using ffprobe"""
    try:
        cmd = [
            'ffprobe', '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'json',
            video_file
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10)
        if result.returncode == 0:
            data = json.loads(result.stdout)
            if 'format' in data and 'duration' in data['format']:
                duration = float(data['format']['duration'])
                return duration
    except Exception as e:
        print(f"Error getting video duration: {e}")
    return None


def parse_bitrate_string(bitrate_str):
    """
    Parse bitrate string from MediaInfo and convert to kbit/s.
    
    Handles formats like:
    - "55.3 Mb/s" -> 55300 kbit/s
    - "9 039 kb/s" -> 9039 kbit/s
    - "1.5 Gb/s" -> 1500000 kbit/s
    
    Args:
        bitrate_str: String representation of bitrate (e.g., "55.3 Mb/s")
        
    Returns:
        int: Bitrate in kbit/s, or None if parsing fails
    """
    if not bitrate_str:
        return None
    
    try:
        # Remove spaces from numbers like "9 039" -> "9039"
        bitrate_str_clean = bitrate_str.replace(' ', '')
        
        # Match patterns like "55.3Mb/s", "9039kb/s", etc.
        match = re.search(r'([\d.]+)(Mb|Gb|Kb|b)/s', bitrate_str_clean, re.IGNORECASE)
        if match:
            value = float(match.group(1))
            unit = match.group(2).lower()
            
            # Convert to kbit/s
            if unit == 'gb':
                return int(value * 1000000)
            elif unit == 'mb':
                return int(value * 1000)
            elif unit == 'kb':
                return int(value)
            elif unit == 'b':
                return int(value / 1000)
    except (ValueError, AttributeError):
        pass
    
    return None



def get_video_bitrate(video_file):
    """Get video bitrate in kbit/s using ffprobe with multiple fallback mechanisms"""
    try:
        # Primary + Fallback 1: Try to get BPS from stream tags (MKV) and bit_rate field (MP4)
        cmd = [
            'ffprobe', '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=bit_rate:stream_tags=BPS',
            '-of', 'json',
            video_file
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10)
        if result.returncode == 0:
            data = json.loads(result.stdout)
            if 'streams' in data and len(data['streams']) > 0:
                stream = data['streams'][0]
                
                # Primary: Try BPS from stream tags (MKV containers)
                tags = stream.get('tags', {})
                bps = tags.get('BPS')
                if bps:
                    # BPS is in bit/s, convert to kbit/s
                    return int(int(bps) / 1000)
                
                # Fallback 1: Try bit_rate field (MP4 and other containers)
                bit_rate = stream.get('bit_rate')
                if bit_rate:
                    # bit_rate is in bit/s, convert to kbit/s
                    return int(int(bit_rate) / 1000)
        
        # Fallback 2: Try format-level bitrate
        cmd = [
            'ffprobe', '-v', 'error',
            '-show_entries', 'format=bit_rate',
            '-of', 'json',
            video_file
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10)
        if result.returncode == 0:
            data = json.loads(result.stdout)
            if 'format' in data:
                format_bitrate = data['format'].get('bit_rate')
                if format_bitrate:
                    # Format bitrate includes all streams, but it's better than nothing
                    # Convert from bit/s to kbit/s
                    return int(int(format_bitrate) / 1000)
        
        # Fallback 3: Try MediaInfo
        cmd = ['mediainfo', '--Output=JSON', video_file]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10)
        if result.returncode == 0:
            data = json.loads(result.stdout)
            if data.get('media') and 'track' in data['media']:
                for track in data['media']['track']:
                    if track.get('@type') == 'Video':
                        # Try BitRate field (in bit/s)
                        bitrate = track.get('BitRate')
                        if bitrate:
                            # Convert from bit/s to kbit/s
                            return int(int(bitrate) / 1000)
                        # Try BitRate_String (e.g., "55.3 Mb/s")
                        bitrate_str = track.get('BitRate_String')
                        if bitrate_str:
                            result = parse_bitrate_string(bitrate_str)
                            if result:
                                return result
    except Exception as e:
        print(f"Error getting video bitrate: {e}")
    return None


def get_audio_bitrate(video_file):
    """Get audio bitrate in kbit/s for the preferred language track using ffprobe with multiple fallback mechanisms"""
    # Get language codes for the configured language and English fallback
    preferred_lang_codes = LANGUAGE_CODE_MAP.get(CONTENT_LANGUAGE, [CONTENT_LANGUAGE.lower()])
    english_lang_codes = LANGUAGE_CODE_MAP.get('en', ['eng', 'en', 'english'])
    
    try:
        # Primary + Fallback 1: Try to get BPS from stream tags (MKV) and bit_rate field (MP4)
        cmd = [
            'ffprobe',
            '-v',
            'error',
            '-select_streams',
            'a',
            '-show_entries',
            'stream=index,bit_rate:stream_tags=language,BPS',
            '-of',
            'json',
            video_file]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10)
        if result.returncode == 0:
            data = json.loads(result.stdout)
            if 'streams' in data and len(data['streams']) > 0:
                # Try to find preferred language audio track first, then English, then first track
                preferred_stream = None
                english_stream = None
                first_stream = None

                for stream in data['streams']:
                    tags = stream.get('tags', {})
                    language = tags.get('language', '').lower()

                    if first_stream is None:
                        first_stream = stream

                    if language in preferred_lang_codes:
                        preferred_stream = stream
                        # If preferred language is English, also set english_stream
                        if language in english_lang_codes:
                            english_stream = stream
                        break
                    
                    if english_stream is None and language in english_lang_codes:
                        english_stream = stream

                # Use preferred language track if found, otherwise English, otherwise first track
                selected_stream = preferred_stream if preferred_stream else (english_stream if english_stream else first_stream)

                if selected_stream:
                    tags = selected_stream.get('tags', {})
                    
                    # Primary: Try BPS from stream tags (MKV containers)
                    bps = tags.get('BPS')
                    if bps:
                        # BPS is in bit/s, convert to kbit/s
                        return int(int(bps) / 1000)
                    
                    # Fallback 1: Try bit_rate field (MP4 and other containers)
                    bit_rate = selected_stream.get('bit_rate')
                    if bit_rate:
                        # Convert from bit/s to kbit/s
                        return int(int(bit_rate) / 1000)
        
        # Fallback 2: Try format-level bitrate (less useful for audio, but worth trying)
        cmd = [
            'ffprobe', '-v', 'error',
            '-show_entries', 'format=bit_rate',
            '-of', 'json',
            video_file
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10)
        if result.returncode == 0:
            data = json.loads(result.stdout)
            if 'format' in data:
                format_bitrate = data['format'].get('bit_rate')
                if format_bitrate:
                    # Format bitrate includes all streams, estimate audio using configured ratio
                    # This is a rough estimate and should only be used as last resort
                    # Convert from bit/s to kbit/s
                    estimated_audio = int(int(format_bitrate) * AUDIO_BITRATE_FORMAT_ESTIMATE_RATIO / 1000)
                    if estimated_audio > 0:
                        return estimated_audio
        
        # Fallback 3: Try MediaInfo
        cmd = ['mediainfo', '--Output=JSON', video_file]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10)
        if result.returncode == 0:
            data = json.loads(result.stdout)
            if data.get('media') and 'track' in data['media']:
                audio_tracks = [track for track in data['media']['track'] if track.get('@type') == 'Audio']
                if audio_tracks:
                    # Try to find preferred language audio track first, then English, then first track
                    preferred_track = None
                    english_track = None
                    first_track = audio_tracks[0] if audio_tracks else None
                    
                    for track in audio_tracks:
                        language = track.get('Language', '').lower()
                        
                        if language in preferred_lang_codes:
                            preferred_track = track
                            if language in english_lang_codes:
                                english_track = track
                            break
                        
                        if english_track is None and language in english_lang_codes:
                            english_track = track
                    
                    # Use preferred language track if found, otherwise English, otherwise first track
                    selected_track = preferred_track if preferred_track else (english_track if english_track else first_track)
                    
                    if selected_track:
                        # Try BitRate field (in bit/s)
                        bitrate = selected_track.get('BitRate')
                        if bitrate:
                            # Convert from bit/s to kbit/s
                            return int(int(bitrate) / 1000)
                        # Try BitRate_String (e.g., "9 039 kb/s")
                        bitrate_str = selected_track.get('BitRate_String')
                        if bitrate_str:
                            result = parse_bitrate_string(bitrate_str)
                            if result:
                                return result
    except Exception as e:
        print(f"Error getting audio bitrate: {e}")
    return None


def get_audio_codec(video_file):
    """Get audio codec with detailed profile info, preferring configured language tracks"""
    # Get language codes for the configured language and English fallback
    preferred_lang_codes = LANGUAGE_CODE_MAP.get(CONTENT_LANGUAGE, [CONTENT_LANGUAGE.lower()])
    english_lang_codes = LANGUAGE_CODE_MAP.get('en', ['eng', 'en', 'english'])
    
    # Try MediaInfo first for better format detection (especially Atmos and
    # DTS:X)
    audio_tracks = get_audio_info_mediainfo(video_file)
    if audio_tracks:
        # Try to find preferred language audio track first, then English, then first track
        preferred_track = None
        english_track = None
        first_track = None

        for track in audio_tracks:
            language = track.get('Language', '').lower()

            if first_track is None:
                first_track = track

            if language in preferred_lang_codes:
                preferred_track = track
                # If preferred language is English, also set english_track
                if language in english_lang_codes:
                    english_track = track
                break
            
            if english_track is None and language in english_lang_codes:
                english_track = track

        # Use preferred language track if found, otherwise English, otherwise first track
        selected_track = preferred_track if preferred_track else (english_track if english_track else first_track)

        if selected_track:
            # Extract format information from MediaInfo
            format_commercial = selected_track.get(
                'Format_Commercial_IfAny', '')
            format_name = selected_track.get('Format', '')
            format_profile = selected_track.get('Format_Profile', '')
            format_additional = selected_track.get(
                'Format_AdditionalFeatures', '')
            title = selected_track.get('Title', '')
            channels = selected_track.get('Channels', '')

            # Get channel format string
            channel_str = get_channel_format(channels)
            channel_suffix = f" {channel_str}" if channel_str else ""

            # Check for IMAX in title
            is_imax = 'imax' in title.lower()

            # Detect formats using MediaInfo's commercial names and format details
            # Dolby Atmos detection
            if 'Dolby Atmos' in format_commercial or 'Atmos' in format_commercial:
                if 'TrueHD' in format_name or 'TrueHD' in format_commercial:
                    return f'Dolby TrueHD{channel_suffix} (Atmos)'
                elif 'E-AC-3' in format_name or 'E-AC-3' in format_commercial:
                    return f'Dolby Digital Plus{channel_suffix} (Atmos)'
                elif 'AC-3' in format_name:
                    return f'Dolby Digital{channel_suffix} (Atmos)'
                else:
                    return f'Dolby Atmos{channel_suffix}'

            # DTS:X detection - check multiple fields before DTS-HD MA
            # Check format_commercial, format_name, format_additional, and
            # title
            if ('DTS:X' in format_commercial or 'DTS-X' in format_commercial or
                'DTS XLL X' in format_name or 'XLL X' in format_name or
                'DTS:X' in format_additional or
                    'DTS:X' in title or 'DTS-X' in title):
                if is_imax:
                    return f'DTS:X (IMAX){channel_suffix}'
                return f'DTS:X{channel_suffix}'

            # Standard format detection based on Format field
            if format_name == 'MLP FBA' or 'TrueHD' in format_name:
                return f'Dolby TrueHD{channel_suffix}'
            elif format_name == 'E-AC-3' or 'E-AC-3' in format_commercial:
                return f'Dolby Digital Plus{channel_suffix}'
            elif format_name == 'AC-3':
                return f'Dolby Digital{channel_suffix}'
            elif 'DTS XLL' in format_name or 'DTS-HD Master Audio' in format_commercial:
                return f'DTS-HD MA{channel_suffix}'
            elif 'DTS XBR' in format_name or 'DTS-HD High Resolution' in format_commercial:
                return f'DTS-HD HRA{channel_suffix}'
            elif format_name == 'DTS':
                if 'DTS-HD' in format_commercial:
                    return f'DTS-HD{channel_suffix}'
                return f'DTS{channel_suffix}'
            elif format_name == 'AAC':
                return f'AAC{channel_suffix}'
            elif format_name == 'FLAC':
                return f'FLAC{channel_suffix}'
            elif format_name == 'MPEG Audio':
                if 'Layer 3' in format_profile:
                    return f'MP3{channel_suffix}'
                return f'MPEG Audio{channel_suffix}'
            elif format_name == 'Opus':
                return f'Opus{channel_suffix}'
            elif format_name == 'Vorbis':
                return f'Vorbis{channel_suffix}'
            elif format_name == 'PCM':
                return f'PCM{channel_suffix}'
            else:
                # Return the format name if we didn't match any specific
                # pattern
                codec_name = format_name if format_name else 'Unknown'
                return f'{codec_name}{channel_suffix}'

    # Fallback to ffprobe if MediaInfo failed
    try:
        cmd = [
            'ffprobe',
            '-v',
            'error',
            '-select_streams',
            'a',
            '-show_entries',
            'stream=index,codec_name,profile,channels:stream_tags=language,title',
            '-of',
            'json',
            video_file]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10)
        if result.returncode == 0:
            data = json.loads(result.stdout)
            if 'streams' in data and len(data['streams']) > 0:
                # Try to find preferred language audio track first, then English, then first track
                preferred_stream = None
                english_stream = None
                first_stream = None

                for stream in data['streams']:
                    tags = stream.get('tags', {})
                    language = tags.get('language', '').lower()

                    if first_stream is None:
                        first_stream = stream

                    if language in preferred_lang_codes:
                        preferred_stream = stream
                        # If preferred language is English, also set english_stream
                        if language in english_lang_codes:
                            english_stream = stream
                        break
                    
                    if english_stream is None and language in english_lang_codes:
                        english_stream = stream

                # Use preferred language track if found, otherwise English, otherwise first track
                selected_stream = preferred_stream if preferred_stream else (english_stream if english_stream else first_stream)

                codec_name = selected_stream.get('codec_name', 'Unknown')
                profile = selected_stream.get('profile', '').lower()
                channels = selected_stream.get('channels', 0)
                tags = selected_stream.get('tags', {})
                title = tags.get('title', '').lower()

                # Get channel format string
                channel_str = get_channel_format(channels)
                channel_suffix = f" {channel_str}" if channel_str else ""

                # Detect Atmos from title or profile
                is_atmos = 'atmos' in title or 'atmos' in profile
                is_imax = 'imax' in title

                # Format codec name with detailed profile information
                if codec_name == 'ac3':
                    return f'Dolby Digital{channel_suffix}'
                elif codec_name == 'eac3':
                    if is_atmos:
                        return f'Dolby Digital Plus (Atmos){channel_suffix}'
                    return f'Dolby Digital Plus{channel_suffix}'
                elif codec_name == 'truehd':
                    if is_atmos:
                        return f'Dolby TrueHD (Atmos){channel_suffix}'
                    return f'Dolby TrueHD{channel_suffix}'
                elif codec_name in ['dts', 'dca']:
                    if 'dts:x' in title or 'dtsx' in title or 'dts-x' in title:
                        if is_imax:
                            return f'DTS:X (IMAX){channel_suffix}'
                        return f'DTS:X{channel_suffix}'
                    elif 'ma' in profile or 'dts-hd ma' in title or 'dts-hd master audio' in title:
                        return f'DTS-HD MA{channel_suffix}'
                    elif 'hra' in profile or 'dts-hd hra' in title or 'dts-hd high resolution' in title:
                        return f'DTS-HD HRA{channel_suffix}'
                    elif 'hd' in profile or 'dts-hd' in title:
                        return f'DTS-HD{channel_suffix}'
                    return f'DTS{channel_suffix}'
                elif codec_name == 'aac':
                    return f'AAC{channel_suffix}'
                elif codec_name == 'flac':
                    return f'FLAC{channel_suffix}'
                elif codec_name == 'mp3':
                    return f'MP3{channel_suffix}'
                elif codec_name == 'opus':
                    return f'Opus{channel_suffix}'
                elif codec_name == 'vorbis':
                    return f'Vorbis{channel_suffix}'
                elif codec_name.startswith('pcm'):
                    return f'PCM{channel_suffix}'
                else:
                    return f'{codec_name.upper()}{channel_suffix}'
    except Exception as e:
        print(f"Error getting audio codec from ffprobe: {e}")
    return "Unknown"


def scan_video_file(file_path):
    """Scan a video file and extract all metadata"""
    print(f"Scanning: {file_path}")

    if file_path in scanned_paths:
        return {
            'success': False,
            'message': 'File already scanned'
        }

    # Detect HDR format
    hdr_info = detect_hdr_format(file_path)
    resolution = get_video_resolution(file_path)
    audio_codec = get_audio_codec(file_path)
    
    # Get additional metadata for media details dialog
    duration = get_video_duration(file_path)
    video_bitrate = get_video_bitrate(file_path)
    audio_bitrate = get_audio_bitrate(file_path)
    file_size = os.path.getsize(file_path)

    # Get poster, title, and year based on IMAGE_SOURCE setting
    filename = os.path.basename(file_path)
    tmdb_id = None
    poster_url = None
    tmdb_title = None
    tmdb_year = None
    tmdb_rating = None
    tmdb_plot = None
    
    if IMAGE_SOURCE == 'fanart':
        # Use Fanart.tv for poster
        tmdb_id, poster_url = get_fanart_poster(filename)
        # Fetch title, year, rating, and plot from TMDB if we have a TMDB ID and API key
        if tmdb_id and TMDB_API_KEY:
            print(f"  [TMDB] Fetching title/year/rating/plot for Fanart.tv poster...")
            # Try movie first - use get_tmdb_poster_by_id to get rating and plot too
            _, tmdb_title, tmdb_year, tmdb_rating, tmdb_plot = get_tmdb_poster_by_id(tmdb_id, 'movie')
            if not tmdb_title:
                # Try TV show
                _, tmdb_title, tmdb_year, tmdb_rating, tmdb_plot = get_tmdb_poster_by_id(tmdb_id, 'tv')
            if tmdb_title:
                print(f"  [TMDB] Title/year/rating found: {tmdb_title} ({tmdb_year}) - Rating: {tmdb_rating}")
    else:
        # Use TMDB (default)
        tmdb_id, poster_url, tmdb_title, tmdb_year, tmdb_rating, tmdb_plot = get_tmdb_poster(filename)

    # Cache the poster if we got a URL
    cached_backdrop_path = None
    if poster_url:
        cached_backdrop_path = get_cached_backdrop_path(tmdb_id, poster_url)

    # Get credits (directors and cast) if we have a TMDB ID
    tmdb_directors = []
    tmdb_cast = []
    if tmdb_id and TMDB_API_KEY:
        print(f"  [TMDB] Fetching credits for TMDB ID: {tmdb_id}")
        # Try movie first
        tmdb_directors, tmdb_cast = get_tmdb_credits(tmdb_id, 'movie')
        if not tmdb_directors and not tmdb_cast:
            # Try TV show
            tmdb_directors, tmdb_cast = get_tmdb_credits(tmdb_id, 'tv')
        if tmdb_directors or tmdb_cast:
            print(f"  [TMDB] Credits found - Directors: {len(tmdb_directors)}, Cast: {len(tmdb_cast)}")

    file_info = {
        'filename': filename,
        'path': file_path,
        'hdr_format': hdr_info.get('format', 'Unknown'),
        'hdr_detail': hdr_info.get('detail', 'Unknown'),
        'profile': hdr_info.get('profile'),
        'el_type': hdr_info.get('el_type'),
        'resolution': resolution,
        'audio_codec': audio_codec,
        'tmdb_id': tmdb_id,
        'poster_url': cached_backdrop_path if cached_backdrop_path else poster_url,
        'tmdb_title': tmdb_title,
        'tmdb_year': tmdb_year,
        'tmdb_rating': tmdb_rating,
        'tmdb_plot': tmdb_plot,
        'tmdb_directors': tmdb_directors,
        'tmdb_cast': tmdb_cast,
        'duration': duration,
        'video_bitrate': video_bitrate,
        'audio_bitrate': audio_bitrate,
        'file_size': file_size
    }

    with scan_lock:
        scanned_files[file_path] = file_info
        scanned_paths.add(file_path)
        save_database()

    print(f"✓ Scanned: {file_path} ({hdr_info.get('format')})")

    return {
        'success': True,
        'message': f'{hdr_info.get("format")} detected',
        'file_info': file_info
    }


def scan_directory(directory):
    """Scan directory for video files"""
    if not os.path.exists(directory):
        print(f"Directory does not exist: {directory}")
        return []

    new_files = []
    for root, dirs, files in os.walk(directory):
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in SUPPORTED_FORMATS:
                file_path = os.path.join(root, file)
                if file_path not in scanned_paths:
                    new_files.append(file_path)

    return new_files


def background_scan_new_files():
    """Background task to scan new files"""
    new_files = scan_directory(MEDIA_PATH)
    print(f"Found {len(new_files)} new files to scan")

    for file_path in new_files:
        try:
            scan_video_file(file_path)
        except Exception as e:
            print(f"Error scanning {file_path}: {e}")


class MediaFileHandler(FileSystemEventHandler):
    """Handle file system events for automatic scanning"""

    def on_created(self, event):
        if event.is_directory:
            return

        file_path = event.src_path
        ext = os.path.splitext(file_path)[1].lower()

        if ext in SUPPORTED_FORMATS:
            print(f"New file detected: {file_path}")
            time.sleep(FILE_WRITE_DELAY)
            try:
                scan_video_file(file_path)
            except Exception as e:
                print(f"Error scanning new file {file_path}: {e}")

    def on_deleted(self, event):
        """Handle file deletion - remove from database"""
        if event.is_directory:
            return

        file_path = event.src_path
        ext = os.path.splitext(file_path)[1].lower()

        if ext in SUPPORTED_FORMATS:
            print(f"File deletion detected: {file_path}")
            with scan_lock:
                if file_path in scanned_files:
                    file_info = scanned_files[file_path]
                    
                    # Delete cached poster if it exists
                    delete_cached_poster(file_info)
                    
                    del scanned_files[file_path]
                    scanned_paths.discard(file_path)
                    save_database()
                    print(f"✗ Removed from database: {file_path}")


def start_file_observer():
    """Start watchdog observer for automatic file scanning"""
    if not os.path.exists(MEDIA_PATH):
        print(f"Creating media directory: {MEDIA_PATH}")
        os.makedirs(MEDIA_PATH, exist_ok=True)

    event_handler = MediaFileHandler()
    observer = Observer()
    observer.schedule(event_handler, MEDIA_PATH, recursive=True)
    observer.start()
    print(f"File observer started for: {MEDIA_PATH}")
    return observer


@app.route('/')
def index():
    """Main page showing scanned files"""
    files_list = list(scanned_files.values())
    # Sort by filename
    files_list.sort(key=lambda x: x['filename'])

    return render_template('index.html',
                           files=files_list,
                           file_count=len(files_list))


@app.route('/scan', methods=['POST'])
def manual_scan():
    """Endpoint for manual scan trigger"""
    try:
        initial_count = len(scanned_files)

        # Clean up database for non-existent files
        removed_count = cleanup_database()

        # Scan for new files
        new_files = scan_directory(MEDIA_PATH)

        # Scan each new file
        scanned_new_count = 0
        for file_path in new_files:
            try:
                result = scan_video_file(file_path)
                if result and result.get('success', False):
                    scanned_new_count += 1
            except Exception as e:
                print(f"Error scanning {file_path}: {e}")

        final_count = len(scanned_files)

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
        for root, dirs, files in os.walk(MEDIA_PATH):
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in SUPPORTED_FORMATS:
                    file_path = os.path.join(root, file)
                    is_scanned = file_path in scanned_paths
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
        data = request.get_json()
        file_path = data.get('file_path')

        if not file_path:
            return jsonify({
                'success': False,
                'error': 'No file path provided'
            }), 400

        if not os.path.exists(file_path):
            return jsonify({
                'success': False,
                'error': 'File not found'
            }), 404

        # Scan the file
        result = scan_video_file(file_path)

        if result:
            return jsonify({
                'success': True,
                'message': f'File scanned successfully',
                'file_info': result
            })
        else:
            return jsonify({
                'success': False,
                'message': 'File was not Profile 7 or already scanned'
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/update_assets', methods=['POST'])
def update_assets():
    """Endpoint to manually trigger asset updates"""
    try:
        success = update_static_files()
        if success:
            return jsonify({
                'success': True,
                'message': 'All assets updated successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to update some assets'
            }), 500
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

        backdrop_path = os.path.join(POSTER_CACHE_DIR, filename)

        # Verify the resolved path is still within POSTER_CACHE_DIR
        if not os.path.abspath(backdrop_path).startswith(
                os.path.abspath(POSTER_CACHE_DIR)):
            print(f"Path traversal attempt detected: {filename}")
            return "Invalid filename", 400

        if os.path.exists(backdrop_path):
            return send_file(backdrop_path, mimetype='image/jpeg')
        else:
            return "Poster not found", 404
    except Exception as e:
        print(f"Error serving poster {filename}: {e}")
        return "Error serving poster", 500


def main():
    """Main application entry point"""
    print("=" * 50)
    print("Starting Universal Video Scanner")
    print("=" * 50)

    # Check and download static files if needed
    print("Checking static files...")
    if not download_static_files():
        print("Warning: Failed to download some static files")

    # Clean up any orphaned temporary files from previous runs
    cleanup_temp_directory()

    # Load existing database
    load_database()

    # Show configured content language
    print(f"Content language: {CONTENT_LANGUAGE.upper()}")

    # Migrate existing poster URLs to cached versions
    if REQUESTS_AVAILABLE:
        print(f"Image source: {IMAGE_SOURCE.upper()}")
        if IMAGE_SOURCE == 'fanart':
            if FANART_API_KEY:
                print("✓ Fanart.tv API key configured")
            else:
                print("⚠ Warning: Fanart.tv selected but FANART_API_KEY not configured - no posters will be fetched")
        elif IMAGE_SOURCE == 'tmdb':
            if TMDB_API_KEY:
                print("✓ TMDB API key configured")
            else:
                print("⚠ Warning: TMDB selected but TMDB_API_KEY not configured - no posters will be fetched")
        else:
            print(f"⚠ Warning: Unknown IMAGE_SOURCE '{IMAGE_SOURCE}' - defaulting to TMDB")
            if TMDB_API_KEY:
                print("✓ TMDB API key configured")
            else:
                print("⚠ Warning: TMDB_API_KEY not configured - no posters will be fetched")
        print("Migrating poster URLs to cache...")
        migrate_poster_urls_to_cache()

    # Clean up database for non-existent files
    removed_count = cleanup_database()
    if removed_count > 0:
        print(f"Cleaned up {removed_count} entries for non-existent files")

    # Start file observer in background
    observer = start_file_observer()

    # Start initial scan automatically in background
    threading.Thread(target=background_scan_new_files, daemon=True).start()
    print("Initial scan started...")

    # Start Flask app
    try:
        app.run(host='0.0.0.0', port=2367, debug=False)
    except KeyboardInterrupt:
        print("Shutting down...")
        observer.stop()
        observer.join()
        # Clean up temp directory on shutdown
        cleanup_temp_directory()


if __name__ == '__main__':
    main()
