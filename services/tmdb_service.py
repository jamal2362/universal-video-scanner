# Copyright (c) 2026 Jamal2367
# Licensed under the MIT License. See LICENSE file in the project root for full license information.
"""
TMDB API Integration Service
Handles all interactions with The Movie Database (TMDB) API
"""
import os
from urllib.parse import urlparse
from utils.regex_patterns import (
    TMDB_ID_PATTERN, YEAR_PATTERN, RESOLUTION_PATTERN,
    CODEC_PATTERN, SOURCE_PATTERN, HDR_PATTERN,
    BRACKET_PATTERN, SEPARATOR_PATTERN, WHITESPACE_PATTERN
)

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


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


def get_tmdb_title_and_year_by_id(tmdb_id, media_type, tmdb_api_key, content_language):
    """Fetch only title and year from TMDB API by ID (without poster)"""
    if not tmdb_api_key or not REQUESTS_AVAILABLE:
        return None, None

    # Validate tmdb_id is numeric
    if not tmdb_id or not isinstance(tmdb_id, (str, int)) or not str(tmdb_id).isdigit():
        print(f"Invalid TMDB ID: {tmdb_id}")
        return None, None

    try:
        url = f'https://api.themoviedb.org/3/{media_type}/{tmdb_id}'

        # Try configured language first
        params = {'api_key': tmdb_api_key, 'language': content_language}
        response = requests.get(url, params=params, timeout=10)

        if response.status_code == 200:
            data = response.json()
            title, year = extract_title_and_year_from_tmdb(data, media_type)
            if title:
                return title, year

        # If configured language request failed, try English fallback
        if content_language != 'en' and response.status_code != 200:
            params = {'api_key': tmdb_api_key, 'language': 'en'}
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


def get_tmdb_poster_by_id(tmdb_id, media_type, tmdb_api_key, content_language):
    """Fetch poster URL, title, year, rating, and plot from TMDB API by ID"""
    if not tmdb_api_key or not REQUESTS_AVAILABLE:
        return None, None, None, None, None

    # Validate tmdb_id is numeric
    if not tmdb_id or not isinstance(
            tmdb_id, (str, int)) or not str(tmdb_id).isdigit():
        print(f"Invalid TMDB ID: {tmdb_id}")
        return None, None, None, None, None

    try:
        url = f'https://api.themoviedb.org/3/{media_type}/{tmdb_id}'

        # Try configured language first
        params = {'api_key': tmdb_api_key, 'language': content_language}
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
        if content_language != 'en' and (response.status_code != 200 or not data.get('backdrop_path')):
            params = {'api_key': tmdb_api_key, 'language': 'en'}
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


def search_tmdb_poster(movie_name, media_type, tmdb_api_key, content_language):
    """Search TMDB for movie/tv show and return poster URL, title, year, rating, and plot"""
    if not tmdb_api_key or not REQUESTS_AVAILABLE or not movie_name:
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
            'api_key': tmdb_api_key,
            'query': movie_name,
            'language': content_language
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
        if content_language != 'en' and (response.status_code != 200 or not results or not results[0].get('backdrop_path')):
            params = {
                'api_key': tmdb_api_key,
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


def get_tmdb_poster(filename, tmdb_api_key, content_language):
    """Main function: Try ID first, then fallback to name search. Returns (tmdb_id, poster_url, title, year, rating, plot)"""
    if not tmdb_api_key or not REQUESTS_AVAILABLE:
        return None, None, None, None, None, None

    # Try to extract TMDB ID first
    tmdb_id = extract_tmdb_id(filename)
    if tmdb_id:
        print(f"  [TMDB] Found TMDB ID: {tmdb_id}")
        # Try movie first
        poster_url, title, year, rating, plot = get_tmdb_poster_by_id(tmdb_id, 'movie', tmdb_api_key, content_language)
        if poster_url:
            print(f"  [TMDB] Poster found by ID (movie): {poster_url}")
            return tmdb_id, poster_url, title, year, rating, plot
        # Try TV show
        poster_url, title, year, rating, plot = get_tmdb_poster_by_id(tmdb_id, 'tv', tmdb_api_key, content_language)
        if poster_url:
            print(f"  [TMDB] Poster found by ID (TV): {poster_url}")
            return tmdb_id, poster_url, title, year, rating, plot

    # Fallback: Search by name
    movie_name = extract_movie_name(filename)
    if movie_name:
        print(f"  [TMDB] Searching by name: '{movie_name}'")
        # Try movie search first
        poster_url, title, year, rating, plot = search_tmdb_poster(movie_name, 'movie', tmdb_api_key, content_language)
        if poster_url:
            print(f"  [TMDB] Poster found by search (movie): {poster_url}")
            return None, poster_url, title, year, rating, plot
        # Try TV search
        poster_url, title, year, rating, plot = search_tmdb_poster(movie_name, 'tv', tmdb_api_key, content_language)
        if poster_url:
            print(f"  [TMDB] Poster found by search (TV): {poster_url}")
            return None, poster_url, title, year, rating, plot

    print(f"  [TMDB] No poster found for: {filename}")
    return None, None, None, None, None, None


def get_tmdb_credits(tmdb_id, media_type, tmdb_api_key):
    """Fetch directors and cast from TMDB API by ID. Returns (directors_list, cast_list)"""
    if not tmdb_api_key or not REQUESTS_AVAILABLE:
        return [], []

    # Validate tmdb_id is numeric
    if not tmdb_id or not isinstance(tmdb_id, (str, int)) or not str(tmdb_id).isdigit():
        print(f"Invalid TMDB ID for credits: {tmdb_id}")
        return [], []

    try:
        url = f'https://api.themoviedb.org/3/{media_type}/{tmdb_id}/credits'
        params = {'api_key': tmdb_api_key}
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
