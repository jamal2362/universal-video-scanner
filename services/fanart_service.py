"""
Fanart.tv API Integration Service
Handles all interactions with Fanart.tv API
"""
from urllib.parse import urlparse
from services.tmdb_service import extract_tmdb_id

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


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


def get_fanart_poster_by_id(tmdb_id, media_type, fanart_api_key, content_language):
    """Fetch thumb poster URL from Fanart.tv API by TMDB ID"""
    if not fanart_api_key or not REQUESTS_AVAILABLE:
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
            print("  [FANART] TV shows not supported (requires TVDB ID)")
            return None

        params = {'api_key': fanart_api_key}
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
                    preferred_thumbs = [t for t in thumbs if t.get('lang', '').lower() == content_language]
                    if preferred_thumbs:
                        preferred_thumbs_sorted = sorted(preferred_thumbs, key=get_likes, reverse=True)
                        thumb_url = preferred_thumbs_sorted[0].get('url')
                        if thumb_url:
                            print(f"  [FANART] Thumb poster found in {content_language}: {thumb_url}")
                            return thumb_url

                    # Fallback to English if no images in preferred language
                    if content_language != 'en':
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


def get_fanart_poster(filename, fanart_api_key, content_language):
    """Main function for Fanart.tv: Try ID first. Returns (tmdb_id, poster_url)"""
    if not fanart_api_key or not REQUESTS_AVAILABLE:
        return None, None

    # Try to extract TMDB ID first (Fanart.tv requires TMDB ID)
    tmdb_id = extract_tmdb_id(filename)
    if tmdb_id:
        print(f"  [FANART] Found TMDB ID: {tmdb_id}")
        # Try movie first
        poster_url = get_fanart_poster_by_id(tmdb_id, 'movie', fanart_api_key, content_language)
        if poster_url:
            print(f"  [FANART] Poster found by ID (movie): {poster_url}")
            return tmdb_id, poster_url
        # Note: TV shows would need TVDB ID, which we don't extract

    print(f"  [FANART] No poster found for: {filename}")
    return None, None
