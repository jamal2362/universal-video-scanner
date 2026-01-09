# Copyright (c) 2026 Jamal2367
# Licensed under the MIT License. See LICENSE file in the project root for full license information.
"""
Poster Service Module
Handles poster caching and downloading
"""
import os
import hashlib
from services.tmdb_service import is_valid_tmdb_url
from services.fanart_service import is_valid_fanart_url

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


def delete_cached_poster(file_info, poster_cache_dir):
    """Delete cached poster file for a given file_info entry"""
    poster_url = file_info.get('poster_url', '')
    if poster_url and poster_url.startswith('/poster/'):
        poster_filename = poster_url.replace('/poster/', '')
        backdrop_path = os.path.join(poster_cache_dir, poster_filename)
        if os.path.exists(backdrop_path):
            try:
                os.remove(backdrop_path)
                print(f"✗ Removed cached poster: {poster_filename}")
            except Exception as e:
                print(f"Error removing poster {poster_filename}: {e}")


def download_and_cache_poster(poster_url, cache_filename, poster_cache_dir):
    """Download poster image and cache it locally"""
    if not poster_url:
        return None

    # Validate URL is from TMDB or Fanart.tv to prevent SSRF attacks
    if not is_valid_tmdb_url(poster_url) and not is_valid_fanart_url(poster_url):
        print(f"  [CACHE] Invalid poster URL (not from TMDB or Fanart.tv): {poster_url}")
        return poster_url

    cache_path = os.path.join(poster_cache_dir, cache_filename)

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
        print("  [CACHE] Timeout downloading poster")
    except requests.exceptions.RequestException as e:
        print(f"  [CACHE] Error downloading poster: {e}")
    except Exception as e:
        print(f"  [CACHE] Unexpected error caching poster: {e}")

    # Return original URL as fallback
    return poster_url


def get_cached_backdrop_path(tmdb_id, poster_url, poster_cache_dir):
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

    return download_and_cache_poster(poster_url, cache_filename, poster_cache_dir)


def migrate_poster_urls_to_cache(scanned_files, scan_lock, save_database_func, poster_cache_dir):
    """Migrate existing TMDB and Fanart.tv poster URLs to cached versions"""
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
                cached_path = get_cached_backdrop_path(tmdb_id, poster_url, poster_cache_dir)
                if cached_path and cached_path.startswith('/poster/'):
                    file_info['poster_url'] = cached_path
                    migrated_count += 1

        if migrated_count > 0:
            save_database_func()
            print(f"✓ Migrated {migrated_count} poster(s) to cache")
