# Copyright (c) 2026 Jamal2367
# Licensed under the MIT License. See LICENSE file in the project root for full license information.
"""
Video Scanner Service Module
Handles video file analysis, HDR detection, and metadata extraction.

Detection is handled exclusively by two fast native probes:
  * hdrprobe   - HDR format (SDR/HDR10/HDR10+/HLG/Dolby Vision), DV profile,
                 enhancement-layer type, CM version, resolution, video bitrate
                 and duration. Replaces dovi_tool + MediaInfo + FFmpeg for video.
  * audioprobe - audio codec, channel layout, language, bitrate and immersive
                 audio format (Dolby Atmos / DTS:X) per track. Replaces
                 MediaInfo + ffprobe for audio (audioprobe >= 0.2.0).
"""
import os
import re
import json
import subprocess
from utils.media_utils import get_channel_format
import config

# Timeout (seconds) for a single probe invocation
PROBE_TIMEOUT = 30


# ---------------------------------------------------------------------------
# Low-level probe helpers
# ---------------------------------------------------------------------------
def _decode_json_object(stdout):
    """
    Decode the first JSON object from probe output, tolerating stray leading
    log text. Works for both hdrprobe (object or single-element array) and
    audioprobe ({"files": [...]}) output.
    """
    if not stdout:
        return None
    start = stdout.find('{')
    if start == -1:
        return None
    try:
        data, _ = json.JSONDecoder().raw_decode(stdout[start:])
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def run_hdrprobe(video_file):
    """
    Run `hdrprobe --json` once.
    Returns (report_dict, first_video_track_dict) or (None, None) on failure.
    """
    try:
        result = subprocess.run(
            ['hdrprobe', '--json', video_file],
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT)
    except FileNotFoundError:
        print("  [hdrprobe] binary not found in PATH")
        return None, None
    except subprocess.TimeoutExpired:
        print(f"  [hdrprobe] timeout for {os.path.basename(video_file)}")
        return None, None
    except Exception as e:
        print(f"  [hdrprobe] error for {os.path.basename(video_file)}: {e}")
        return None, None

    report = _decode_json_object(result.stdout)
    if not report:
        print(f"  [hdrprobe] no parsable output for {os.path.basename(video_file)}")
        return None, None

    tracks = report.get('video_tracks') or []
    video_track = tracks[0] if tracks else None
    return report, video_track


def run_audioprobe(video_file):
    """
    Run `audioprobe --json` once.
    Returns a list of audio-track dicts (may be empty).
    """
    try:
        result = subprocess.run(
            ['audioprobe', '--json', video_file],
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT)
    except FileNotFoundError:
        print("  [audioprobe] binary not found in PATH")
        return []
    except subprocess.TimeoutExpired:
        print(f"  [audioprobe] timeout for {os.path.basename(video_file)}")
        return []
    except Exception as e:
        print(f"  [audioprobe] error for {os.path.basename(video_file)}: {e}")
        return []

    report = _decode_json_object(result.stdout)
    if not report:
        return []

    files = report.get('files')
    if not isinstance(files, list) or not files:
        return []
    tracks = files[0].get('audio_tracks')
    return tracks if isinstance(tracks, list) else []


# ---------------------------------------------------------------------------
# HDR / video derivation (hdrprobe)
# ---------------------------------------------------------------------------
def _compact_cm_version(value):
    """Collapse hdrprobe's 'CM v2.9' / 'CM v4.0' into the app's compact form."""
    if not value:
        return ''
    low = value.lower()
    has29 = '2.9' in low
    has40 = '4.0' in low
    if has29 and has40:
        return 'CMv2.9/4.0'
    if has40:
        return 'CMv4.0'
    if has29:
        return 'CMv2.9'
    return ''


def hdr_info_from_track(video_track):
    """
    Derive the HDR info dict from an hdrprobe video track.

    The returned 'format' strings and 'DV Profile X.Y' detail are kept
    byte-compatible with the existing template/JS badge and sort logic.
    """
    if not video_track:
        return {'format': 'Unknown', 'detail': 'Error',
                'profile': '', 'el_type': '', 'cm_version': ''}

    hdr = video_track.get('hdr') or {}
    fmt_str = (hdr.get('format') or '')
    fmt_low = fmt_str.lower()

    dovi = video_track.get('dolby_vision')
    hdr10plus = video_track.get('hdr10plus')

    # --- Dolby Vision (highest priority) ---
    if dovi:
        profile_raw = (dovi.get('profile') or '').strip()
        match = re.match(r'[0-9]+(?:\.[0-9]+)?', profile_raw)
        profile = match.group(0) if match else profile_raw
        el_type = (dovi.get('el_type') or '').upper()
        cm_version = _compact_cm_version(dovi.get('cm_version'))
        detail = f'DV Profile {profile}' if profile else 'Dolby Vision'
        print(
            f"  -> Dolby Vision (Profile {profile or '?'}, "
            f"EL: {el_type or 'None'}, CM: {cm_version or 'None'})")
        return {
            'format': 'Dolby Vision',
            'profile': profile,
            'el_type': el_type,
            'cm_version': cm_version,
            'detail': detail,
        }

    # --- HDR10+ (dynamic metadata) ---
    if hdr10plus or 'hdr10+' in fmt_low or 'hdr10plus' in fmt_low:
        print("  -> HDR10+ detected")
        return {'format': 'HDR10+', 'detail': 'HDR10+',
                'profile': 'HDR10+', 'el_type': '', 'cm_version': ''}

    # --- HLG ---
    if 'hlg' in fmt_low:
        print("  -> HLG detected")
        return {'format': 'HLG', 'detail': 'HLG',
                'profile': '', 'el_type': '', 'cm_version': ''}

    # --- HDR10 / generic HDR static metadata ---
    if 'hdr10' in fmt_low or 'hdr' in fmt_low:
        print("  -> HDR10 detected")
        return {'format': 'HDR10', 'detail': 'HDR10',
                'profile': '', 'el_type': '', 'cm_version': ''}

    # --- SDR (default) ---
    print("  -> No HDR metadata found: assuming SDR")
    return {'format': 'SDR', 'detail': 'SDR',
            'profile': '', 'el_type': '', 'cm_version': ''}


def resolution_from_track(video_track):
    """Map hdrprobe width/height to a friendly resolution name."""
    if not video_track:
        return "Unknown"

    width = video_track.get('width') or 0
    height = video_track.get('height') or 0
    if not width or not height:
        return "Unknown"

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
    return f"{width}x{height}"


def video_bitrate_from_track(video_track):
    """Return the video bitrate in kbit/s from hdrprobe, or None."""
    if not video_track:
        return None
    bitrate = video_track.get('bitrate') or {}
    bps = bitrate.get('bits_per_sec')
    if bps:
        try:
            return int(float(bps) / 1000)
        except (ValueError, TypeError):
            return None
    return None


# ---------------------------------------------------------------------------
# Audio derivation (audioprobe)
# ---------------------------------------------------------------------------
def _normalize_audio_tracks(ap_tracks):
    """
    Normalize audioprobe (>= 0.2.0) tracks into the internal shape used by the
    scoring / selection / display helpers.

    audioprobe reports object-based audio in a dedicated 'immersive' field
    ('Atmos' / 'DTS:X' / null) and the bitrate (bit/s) directly, so no second
    tool is needed. IMAX Enhanced tracks are flagged from the track title,
    since audioprobe does not classify them.
    """
    normalized = []
    for t in ap_tracks:
        immersive = (t.get('immersive') or '').lower()
        title = (t.get('title') or '')
        normalized.append({
            'codec': t.get('codec') or '',
            'channels': t.get('channels') or 0,
            'layout': t.get('layout') or '',
            'language': (t.get('language') or '').lower(),
            'is_atmos': immersive == 'atmos',
            'is_dtsx': ('dts:x' in immersive or 'dts-x' in immersive or 'dtsx' in immersive),
            'is_imax': 'imax' in title.lower(),
            'bitrate': t.get('bitrate'),
        })
    return normalized


def _audio_quality_score(track):
    """Quality score for a normalized audio track. Higher = better."""
    c = (track.get('codec') or '').lower()
    is_atmos = track.get('is_atmos')
    is_dtsx = track.get('is_dtsx')

    # Object-based audio with lossless base codec (highest quality)
    if is_atmos and ('truehd' in c or c == 'mlp'):
        return 1000
    if is_dtsx and 'dts-hd ma' in c:
        return 1000

    # Object-based audio with lossy base codec
    if is_dtsx:
        return 950
    if is_atmos and 'e-ac-3' in c:
        return 900
    if is_atmos and ('ac-3' in c or c == 'ac3'):
        return 850
    if is_atmos:
        return 900

    # Lossless
    if 'dts-hd ma' in c:
        return 700
    if 'truehd' in c or c == 'mlp':
        return 700
    if 'flac' in c:
        return 650
    if 'pcm' in c or 'lpcm' in c:
        return 650
    if 'alac' in c:
        return 640

    # High-resolution lossy
    if 'dts-hd hra' in c:
        return 600

    # Standard lossy
    if c.startswith('dts'):
        return 500
    if 'e-ac-3' in c:
        return 400
    if 'ac-3' in c or c == 'ac3':
        return 300
    if 'aac' in c:
        return 250
    if 'opus' in c:
        return 200
    if 'vorbis' in c:
        return 150
    if c in ('mp1', 'mp2', 'mp3') or 'mpeg' in c:
        return 100
    return 0


def _select_best_audio(merged):
    """
    Select the best audio track: preferred language, then English, then any;
    within each group by codec quality, then channel count.
    """
    if not merged:
        return None

    preferred_lang_codes = config.LANGUAGE_CODE_MAP.get(
        config.CONTENT_LANGUAGE, [config.CONTENT_LANGUAGE.lower()])
    english_lang_codes = config.LANGUAGE_CODE_MAP.get(
        'en', ['eng', 'en', 'english'])

    def channels_of(t):
        try:
            return int(t.get('channels') or 0)
        except (ValueError, TypeError):
            return 0

    def best_of(group):
        if not group:
            return None
        return max(group, key=lambda t: (
            _audio_quality_score(t), channels_of(t)))

    preferred = [t for t in merged if t['language'] in preferred_lang_codes]
    english = [t for t in merged if t['language'] in english_lang_codes]

    return best_of(preferred) or best_of(english) or best_of(merged)


def _channel_suffix(track):
    """Prefer audioprobe's LFE-aware layout, fall back to channel-count map."""
    layout = (track.get('layout') or '').strip()
    if layout:
        return f" {layout}"
    channel_str = get_channel_format(track.get('channels'))
    return f" {channel_str}" if channel_str else ""


def _audio_display_name(track):
    """
    Build the audio codec display string. Names are kept identical to the
    previous MediaInfo/ffprobe output so the UI's substring-based audio
    sorting (truehd+atmos, dts:x, digital plus, ...) keeps working.
    """
    if not track:
        return "Unknown"

    codec = track.get('codec') or ''
    c = codec.lower()
    cs = _channel_suffix(track)
    is_atmos = track.get('is_atmos')
    is_dtsx = track.get('is_dtsx')
    is_imax = track.get('is_imax')

    # Object-based audio (Atmos)
    if is_atmos:
        if 'truehd' in c or c == 'mlp':
            return f'Dolby TrueHD{cs} (Atmos)'
        if 'e-ac-3' in c or 'eac3' in c:
            return f'Dolby Digital Plus{cs} (Atmos)'
        if 'ac-3' in c or c == 'ac3':
            return f'Dolby Digital{cs} (Atmos)'
        return f'Dolby Atmos{cs}'

    # Object-based audio (DTS:X)
    if is_dtsx:
        if is_imax:
            return f'DTS:X (IMAX){cs}'
        return f'DTS:X{cs}'

    # Base codecs
    if 'truehd' in c or c == 'mlp':
        return f'Dolby TrueHD{cs}'
    if 'e-ac-3' in c or 'eac3' in c:
        return f'Dolby Digital Plus{cs}'
    if 'ac-3' in c or c == 'ac3':
        return f'Dolby Digital{cs}'
    if 'dts-hd ma' in c:
        return f'DTS-HD MA{cs}'
    if 'dts-hd hra' in c:
        return f'DTS-HD HRA{cs}'
    if c.startswith('dts'):
        return f'DTS{cs}'
    if 'aac' in c:
        return f'AAC{cs}'
    if 'flac' in c:
        return f'FLAC{cs}'
    if c in ('mp1', 'mp2', 'mp3') or 'mpeg' in c:
        return f'MP3{cs}'
    if 'opus' in c:
        return f'Opus{cs}'
    if 'vorbis' in c:
        return f'Vorbis{cs}'
    if 'pcm' in c or 'lpcm' in c:
        return f'PCM{cs}'
    if 'alac' in c:
        return f'ALAC{cs}'

    return f'{codec}{cs}' if codec else "Unknown"


def _audio_bitrate_from_track(track):
    """Return audio bitrate in kbit/s from the selected audioprobe track."""
    if not track:
        return None
    bitrate = track.get('bitrate')
    if bitrate:
        try:
            return int(int(bitrate) / 1000)
        except (ValueError, TypeError):
            return None
    return None


# ---------------------------------------------------------------------------
# Public scan entry points
# ---------------------------------------------------------------------------
def scan_video_file(file_path, scanned_paths, scanned_files, scan_lock, save_database_func,
                    get_fanart_poster_func, get_tmdb_poster_func, get_tmdb_poster_by_id_func,
                    get_tmdb_credits_func, get_cached_backdrop_path_func):
    """Scan a video file and extract all metadata"""
    print(f"Scanning: {file_path}")

    if file_path in scanned_paths:
        return {
            'success': False,
            'message': 'File already scanned'
        }

    # --- Video / HDR analysis via hdrprobe (single invocation) ---
    print(f"[HDR] Analyzing: {os.path.basename(file_path)}")
    hdr_report, video_track = run_hdrprobe(file_path)
    hdr_info = hdr_info_from_track(video_track)
    resolution = resolution_from_track(video_track)
    video_bitrate = video_bitrate_from_track(video_track)
    duration = hdr_report.get('duration_secs') if hdr_report else None

    # --- Audio analysis via audioprobe (codec, layout, language, bitrate,
    #     immersive Atmos/DTS:X) ---
    audio_tracks = _normalize_audio_tracks(run_audioprobe(file_path))
    selected_audio = _select_best_audio(audio_tracks)
    audio_codec = _audio_display_name(selected_audio) if selected_audio else "Unknown"
    audio_bitrate = _audio_bitrate_from_track(selected_audio)

    file_size = os.path.getsize(file_path)

    # Get poster, title, and year based on IMAGE_SOURCE setting
    filename = os.path.basename(file_path)
    tmdb_id = None
    poster_url = None
    tmdb_title = None
    tmdb_year = None
    tmdb_rating = None
    tmdb_plot = None

    if config.IMAGE_SOURCE == 'fanart':
        # Use Fanart.tv for poster
        tmdb_id, poster_url = get_fanart_poster_func(filename)
        # Fetch title, year, rating, and plot from TMDB if we have a TMDB ID and API key
        if tmdb_id and config.TMDB_API_KEY:
            print("  [TMDB] Fetching title/year/rating/plot for Fanart.tv poster...")
            # Try movie first - use get_tmdb_poster_by_id to get rating and plot too
            _, tmdb_title, tmdb_year, tmdb_rating, tmdb_plot = get_tmdb_poster_by_id_func(tmdb_id, 'movie')
            if not tmdb_title:
                # Try TV show
                _, tmdb_title, tmdb_year, tmdb_rating, tmdb_plot = get_tmdb_poster_by_id_func(tmdb_id, 'tv')
            if tmdb_title:
                print(f"  [TMDB] Title/year/rating found: {tmdb_title} ({tmdb_year}) - Rating: {tmdb_rating}")
    else:
        # Use TMDB (default)
        tmdb_id, poster_url, tmdb_title, tmdb_year, tmdb_rating, tmdb_plot = get_tmdb_poster_func(filename)

    # Cache the poster if we got a URL
    cached_backdrop_path = None
    if poster_url:
        cached_backdrop_path = get_cached_backdrop_path_func(tmdb_id, poster_url)

    # Get credits (directors and cast) if we have a TMDB ID
    tmdb_directors = []
    tmdb_cast = []
    if tmdb_id and config.TMDB_API_KEY:
        print(f"  [TMDB] Fetching credits for TMDB ID: {tmdb_id}")
        # Try movie first
        tmdb_directors, tmdb_cast = get_tmdb_credits_func(tmdb_id, 'movie')
        if not tmdb_directors and not tmdb_cast:
            # Try TV show
            tmdb_directors, tmdb_cast = get_tmdb_credits_func(tmdb_id, 'tv')
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
        'file_size': file_size,
        'dv_cm_version': hdr_info.get('cm_version', '')
    }

    with scan_lock:
        scanned_files[file_path] = file_info
        scanned_paths.add(file_path)
        save_database_func()

    print(f"✓ Scanned: {file_path} ({hdr_info.get('format')})")

    return {
        'success': True,
        'message': f'{hdr_info.get("format")} detected',
        'file_info': file_info
    }


def scan_directory(directory, scanned_paths):
    """Scan directory for video files"""
    if not os.path.exists(directory):
        print(f"Directory does not exist: {directory}")
        return []

    new_files = []
    for root, dirs, files in os.walk(directory):
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in config.SUPPORTED_FORMATS:
                file_path = os.path.join(root, file)
                if file_path not in scanned_paths:
                    new_files.append(file_path)

    return new_files


def background_scan_new_files(scanned_paths, scan_video_file_func):
    """Background task to scan new files"""
    new_files = scan_directory(config.MEDIA_PATH, scanned_paths)
    print(f"Found {len(new_files)} new files to scan")

    for file_path in new_files:
        try:
            scan_video_file_func(file_path)
        except Exception as e:
            print(f"Error scanning {file_path}: {e}")
