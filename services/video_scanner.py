# Copyright (c) 2026 Jamal2367
# Licensed under the MIT License. See LICENSE file in the project root for full license information.
"""
Video Scanner Service Module
Handles video file analysis, HDR detection, and metadata extraction
"""
import os
import json
import tempfile
import subprocess
from utils.media_utils import (
    get_channel_format, parse_bitrate_string,
    parse_mediainfo_int, parse_mediainfo_float
)
import config


def run_hdrprobe(video_file):
    """
    Run hdrprobe once and return the parsed JSON report, or None on failure.

    hdrprobe handles disc images (.iso) natively: it reads the disc's
    playlists, picks the main feature automatically and reports on it as if
    the underlying .m2ts stream file had been probed directly.
    """
    try:
        print(f"[HDR] Analyzing: {os.path.basename(video_file)}")

        cmd = ['hdrprobe', '--format', 'json', video_file]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120)

        if result.returncode != 0:
            stderr = (result.stderr or '').strip()
            print(
                f"  [HDR] hdrprobe failed for "
                f"{os.path.basename(video_file)}: {stderr}")
            return None

        return json.loads(result.stdout)

    except subprocess.TimeoutExpired:
        print(f"  [HDR] hdrprobe timed out for {os.path.basename(video_file)}")
    except json.JSONDecodeError as e:
        print(f"  [HDR] Failed to parse hdrprobe JSON output: {e}")
    except FileNotFoundError:
        print("  [HDR] hdrprobe not installed / not available in PATH")
    except Exception as e:
        print(f"  [HDR] Unexpected error while running hdrprobe: {e}")
    return None


def detect_hdr_format(video_file, report=None):
    """
    Detect HDR format using hdrprobe: SDR, HDR10, HDR10+, HLG, Dolby Vision (FEL/MEL)
    Returns dict with 'format', 'detail', 'profile', 'el_type', 'cm_version'

    If a pre-fetched hdrprobe ``report`` is provided it is reused, otherwise
    hdrprobe is invoked for ``video_file``.
    """
    try:
        if report is None:
            report = run_hdrprobe(video_file)

        if not report:
            return {'format': 'Unknown', 'detail': 'Error', 'profile': '', 'el_type': '', 'cm_version': ''}

        tracks = report.get('video_tracks') or []
        if not tracks:
            print("  [HDR] hdrprobe returned no video tracks")
            return {'format': 'Unknown', 'detail': 'Error', 'profile': '', 'el_type': '', 'cm_version': ''}

        track = tracks[0]
        hdr = track.get('hdr') or {}
        hdr_format = (hdr.get('format') or '').strip()
        fmt_lower = hdr_format.lower()

        # --- Dolby Vision ---
        dv = track.get('dolby_vision')
        if dv:
            # hdrprobe reports profile as e.g. "8.1", "5.0", "7.6 (FEL)"
            raw_profile = str(dv.get('profile') or '').strip()
            profile = raw_profile.split(' (')[0]
            el_type = (dv.get('el_type') or '').upper()
            # Normalize "CM v4.0" / "CM v2.9" -> "CMv4.0" / "CMv2.9"
            cm_version = ''.join((dv.get('cm_version') or '').split())
            detail = f'DV Profile {profile}' if profile else 'Dolby Vision'
            print(
                f"  -> Dolby Vision detected: Profile {profile or 'Unknown'}, "
                f"EL Type: {el_type or 'None'}, CM Version: {cm_version or 'None'}")
            return {
                'format': 'Dolby Vision',
                'profile': profile,
                'el_type': el_type,
                'cm_version': cm_version,
                'detail': detail
            }

        # --- HDR10+ (must be checked before HDR10) ---
        hdr10plus = track.get('hdr10plus') or {}
        if 'hdr10+' in fmt_lower or hdr10plus:
            # hdrprobe reports the HDR10+ profile as "A" (histogram only)
            # or "B" (Bezier tone-mapping curve) when it can be determined
            hp_profile = str(hdr10plus.get('profile') or '').strip().upper()
            detail = f'HDR10+ Profile {hp_profile}' if hp_profile else 'HDR10+'
            print(f"  -> {detail} detected (hdrprobe: '{hdr_format}')")
            return {'format': 'HDR10+', 'detail': detail, 'profile': hp_profile, 'el_type': '', 'cm_version': ''}

        # --- SL-HDR1 / SL-HDR2 / SL-HDR3 ---
        sl_hdr = track.get('sl_hdr') or {}
        if 'sl-hdr' in fmt_lower or sl_hdr:
            # hdrprobe reports the mode as integer: 1 (SDR base), 2 (PQ base), 3 (HLG base)
            mode = sl_hdr.get('mode')
            if mode in (1, 2, 3):
                name = f'SL-HDR{mode}'
            else:
                name = next(
                    (c for c in ('SL-HDR1', 'SL-HDR2', 'SL-HDR3') if c.lower() in fmt_lower),
                    'SL-HDR')
            print(f"  -> {name} detected (hdrprobe: '{hdr_format}')")
            return {'format': name, 'detail': name, 'profile': '', 'el_type': '', 'cm_version': ''}

        # --- HDR Vivid ---
        if 'vivid' in fmt_lower or track.get('hdr_vivid'):
            print(f"  -> HDR Vivid detected (hdrprobe: '{hdr_format}')")
            return {'format': 'HDR Vivid', 'detail': 'HDR Vivid', 'profile': '', 'el_type': '', 'cm_version': ''}

        # --- HLG ---
        if 'hlg' in fmt_lower:
            print("  -> HLG detected")
            return {'format': 'HLG', 'detail': 'HLG', 'profile': '', 'el_type': '', 'cm_version': ''}

        # --- HDR10 ---
        if 'hdr10' in fmt_lower:
            print("  -> HDR10 detected")
            return {'format': 'HDR10', 'detail': 'HDR10', 'profile': '', 'el_type': '', 'cm_version': ''}

        # --- SDR ---
        if 'sdr' in fmt_lower:
            print("  -> SDR detected")
            return {'format': 'SDR', 'detail': 'SDR', 'profile': '', 'el_type': '', 'cm_version': ''}

        # Other formats reported by hdrprobe (e.g. SL-HDR, HDR Vivid)
        if hdr_format:
            print(f"  -> {hdr_format} detected")
            return {'format': hdr_format, 'detail': hdr_format, 'profile': '', 'el_type': '', 'cm_version': ''}

        # Final fallback: SDR
        print("  -> No HDR metadata found: assuming SDR")
        return {'format': 'SDR', 'detail': 'SDR', 'profile': '', 'el_type': '', 'cm_version': ''}

    except Exception as e:
        print(f"  [HDR] Unexpected error while detecting HDR format: {e}")
        return {'format': 'Unknown', 'detail': 'Error', 'profile': '', 'el_type': '', 'cm_version': ''}


def get_media_info(video_file):
    """
    Run MediaInfo once for a file and return the parsed track list.
    Returns [] if MediaInfo fails or the file has no tracks.
    """
    try:
        cmd = ['mediainfo', '--Output=JSON', video_file]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30)
        if result.returncode == 0 and result.stdout:
            data = json.loads(result.stdout)
            media = data.get('media') or {}
            return media.get('track') or []
        print(
            f"MediaInfo failed for {os.path.basename(video_file)}: "
            f"{(result.stderr or '').strip()}")
    except subprocess.TimeoutExpired:
        print(f"MediaInfo timed out for {os.path.basename(video_file)}")
    except json.JSONDecodeError as e:
        print(f"Failed to parse MediaInfo JSON output: {e}")
    except FileNotFoundError:
        print("MediaInfo not installed / not available in PATH")
    except Exception as e:
        print(f"Error running MediaInfo: {e}")
    return []


# Read size for streaming the ISO sample out of 7z (1 MiB)
_ISO_SAMPLE_CHUNK = 1024 * 1024


def _list_iso_m2ts(iso_path):
    """
    List the .m2ts streams inside a Blu-ray disc image using 7z.

    Returns a list of (path_in_image, size_bytes) tuples, or [] if 7z is not
    available or the image cannot be read.
    """
    try:
        result = subprocess.run(
            ['7z', 'l', '-slt', '-ba', iso_path],
            capture_output=True,
            text=True,
            timeout=120)
        if result.returncode != 0:
            print(f"  [ISO] 7z listing failed: {(result.stderr or '').strip()}")
            return []
    except FileNotFoundError:
        print("  [ISO] 7z (p7zip) not installed / not available in PATH")
        return []
    except subprocess.TimeoutExpired:
        print("  [ISO] 7z listing timed out")
        return []
    except Exception as e:
        print(f"  [ISO] Error listing disc image contents: {e}")
        return []

    entries = []
    path = None
    size = None
    for line in result.stdout.splitlines():
        if line.startswith('Path = '):
            path = line[len('Path = '):].strip()
        elif line.startswith('Size = '):
            size = line[len('Size = '):].strip()
        elif not line.strip():
            # Blank line terminates a file's property block
            if path and path.lower().endswith('.m2ts'):
                try:
                    entries.append((path, int(size)))
                except (TypeError, ValueError):
                    pass
            path = None
            size = None

    # Flush a trailing block that had no terminating blank line
    if path and path.lower().endswith('.m2ts'):
        try:
            entries.append((path, int(size)))
        except (TypeError, ValueError):
            pass

    return entries


def _stop_process(proc):
    """Best-effort teardown of a still-running subprocess"""
    if proc is None:
        return
    try:
        if proc.stdout:
            proc.stdout.close()
    except Exception:
        pass
    try:
        proc.terminate()
        proc.wait(timeout=30)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def extract_iso_m2ts_sample(iso_path, clip_hint=None):
    """
    Extract a prefix sample of the main-feature .m2ts from a Blu-ray disc
    image so MediaInfo can read the audio/video tracks reliably.

    hdrprobe already selects the main feature; its clip name is passed as
    ``clip_hint``. If that clip cannot be matched, the largest .m2ts in the
    image is used (the main movie is almost always the biggest stream).

    Only the first ``config.ISO_SAMPLE_SIZE_MB`` megabytes are written, which
    is enough for MediaInfo to identify every stream without extracting the
    whole (multi-gigabyte) file. Returns the path to a temporary sample file
    that the caller must delete, or None on failure.
    """
    entries = _list_iso_m2ts(iso_path)
    if not entries:
        return None

    target = None
    if clip_hint:
        hint = os.path.basename(clip_hint).lower()
        target = next(
            (p for p, _ in entries if os.path.basename(p).lower() == hint), None)
    if not target:
        # Largest .m2ts is almost always the main feature
        target = max(entries, key=lambda entry: entry[1])[0]

    sample_bytes = max(1, config.ISO_SAMPLE_SIZE_MB) * 1024 * 1024
    print(f"  [ISO] Extracting {config.ISO_SAMPLE_SIZE_MB} MB sample from {target}")

    fd, sample_path = tempfile.mkstemp(prefix='iso_sample_', suffix='.m2ts')
    out = os.fdopen(fd, 'wb')
    proc = None
    try:
        proc = subprocess.Popen(
            ['7z', 'e', '-so', iso_path, target],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL)

        written = 0
        while written < sample_bytes:
            chunk = proc.stdout.read(min(_ISO_SAMPLE_CHUNK, sample_bytes - written))
            if not chunk:
                break
            out.write(chunk)
            written += len(chunk)
        out.close()

        if written == 0:
            print("  [ISO] Sample extraction produced no data")
        else:
            return sample_path
    except FileNotFoundError:
        print("  [ISO] 7z (p7zip) not installed / not available in PATH")
    except Exception as e:
        print(f"  [ISO] Error extracting sample: {e}")
    finally:
        if not out.closed:
            out.close()
        _stop_process(proc)

    # Only reached on failure - clean up the empty/partial temp file
    try:
        os.remove(sample_path)
    except OSError:
        pass
    return None


def get_general_track(tracks):
    """Get the General track from a MediaInfo track list"""
    return next((t for t in tracks if t.get('@type') == 'General'), {})


def get_video_track(tracks):
    """Get the first Video track from a MediaInfo track list"""
    return next((t for t in tracks if t.get('@type') == 'Video'), {})


def get_audio_tracks(tracks):
    """Get all Audio tracks from a MediaInfo track list"""
    return [t for t in tracks if t.get('@type') == 'Audio']


def resolution_name(width, height):
    """Map pixel width/height to a friendly resolution name"""
    if not width or not height:
        return "Unknown"

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


def get_video_resolution(tracks):
    """Get video resolution from MediaInfo tracks and return friendly name"""
    video = get_video_track(tracks)
    width = parse_mediainfo_int(video.get('Width'))
    height = parse_mediainfo_int(video.get('Height'))
    return resolution_name(width, height)


def get_hdrprobe_video_track(report):
    """Get the first video track dict from an hdrprobe report"""
    tracks = (report or {}).get('video_tracks') or []
    return tracks[0] if tracks else {}


def get_hdrprobe_resolution(report):
    """Get the friendly resolution name from an hdrprobe report"""
    track = get_hdrprobe_video_track(report)
    width = parse_mediainfo_int(track.get('width'))
    height = parse_mediainfo_int(track.get('height'))
    return resolution_name(width, height)


def get_hdrprobe_duration(report):
    """Get the file-level duration in seconds from an hdrprobe report"""
    return parse_mediainfo_float((report or {}).get('duration_secs'))


def get_hdrprobe_video_bitrate(report):
    """Get the video bitrate in kbit/s from an hdrprobe report"""
    track = get_hdrprobe_video_track(report)
    bitrate = track.get('bitrate') or {}
    bits_per_sec = parse_mediainfo_float(bitrate.get('bits_per_sec'))
    if bits_per_sec:
        return int(bits_per_sec / 1000)
    return None


def get_hdrprobe_main_clip(report):
    """
    Get the main-feature clip that hdrprobe selected from a disc image.

    For .iso inputs hdrprobe reports a ``bd_iso`` object naming the playlist
    and the .m2ts clip under BDMV/STREAM it probed. Returns None for
    non-disc inputs.
    """
    bd_iso = (report or {}).get('bd_iso') or {}
    return bd_iso.get('clip')


def get_video_duration(tracks):
    """Get video duration in seconds from MediaInfo tracks"""
    # General track duration covers the whole container
    duration = parse_mediainfo_float(get_general_track(tracks).get('Duration'))
    if duration:
        return duration

    # Fallback: duration of the video track
    return parse_mediainfo_float(get_video_track(tracks).get('Duration'))


def _track_bitrate_kbps(track, tracks):
    """
    Get the bitrate of a single MediaInfo track in kbit/s.

    Tries BitRate, BitRate_Nominal, BitRate_String, and finally
    computes from StreamSize and duration. Returns None if unknown.
    """
    if not track:
        return None

    # BitRate / BitRate_Nominal are in bit/s
    for field in ('BitRate', 'BitRate_Nominal'):
        bitrate = parse_mediainfo_int(track.get(field))
        if bitrate:
            return int(bitrate / 1000)

    # BitRate_String (e.g., "55.3 Mb/s")
    parsed = parse_bitrate_string(track.get('BitRate_String'))
    if parsed:
        return parsed

    # Compute from stream size (bytes) and duration (seconds)
    stream_size = parse_mediainfo_int(track.get('StreamSize'))
    duration = parse_mediainfo_float(track.get('Duration')) or get_video_duration(tracks)
    if stream_size and duration:
        return int(stream_size * 8 / duration / 1000)

    return None


def get_video_bitrate(tracks):
    """Get video bitrate in kbit/s from MediaInfo tracks with fallbacks"""
    bitrate = _track_bitrate_kbps(get_video_track(tracks), tracks)
    if bitrate:
        return bitrate

    # Last resort: overall container bitrate (includes all streams)
    overall = parse_mediainfo_int(get_general_track(tracks).get('OverallBitRate'))
    if overall:
        return int(overall / 1000)

    return None


def get_channel_count(track):
    """
    Extract the channel count from a MediaInfo audio track.

    Returns:
        int: Number of channels, or 0 if unable to parse
    """
    return parse_mediainfo_int(track.get('Channels')) or 0


def get_codec_quality_score(track):
    """
    Get a quality score for an audio codec. Higher score = better quality.

    Args:
        track: MediaInfo audio track dict

    Returns:
        int: Quality score (higher is better)
    """
    format_commercial = track.get('Format_Commercial_IfAny', '').upper()
    format_name = track.get('Format', '').upper()
    format_additional = track.get('Format_AdditionalFeatures', '').upper()
    title = track.get('Title', '').upper()

    # Check for DTS:X variants (check before other DTS formats)
    is_dtsx = ('DTS:X' in format_commercial or 'DTS-X' in format_commercial or
               'DTS XLL X' in format_name or 'XLL X' in format_name or
               'DTS:X' in format_additional or 'DTS:X' in title or 'DTS-X' in title)

    # Check for Dolby Atmos variants (check before other Dolby formats)
    is_atmos = 'DOLBY ATMOS' in format_commercial or 'ATMOS' in format_commercial

    # Object-based audio with lossless base codec (highest quality)
    if is_atmos and ('TRUEHD' in format_name or 'TRUEHD' in format_commercial or 'MLP FBA' in format_name):
        return 1000  # TrueHD Atmos
    if is_dtsx and ('DTS XLL' in format_name or 'DTS-HD MASTER AUDIO' in format_commercial):
        return 1000  # DTS-HD MA with DTS:X

    # Object-based audio with lossy base codec
    if is_dtsx:
        return 950  # DTS:X (non-MA variant)
    if is_atmos and ('E-AC-3' in format_name or 'E-AC-3' in format_commercial):
        return 900  # E-AC-3 Atmos
    if is_atmos and format_name == 'AC-3':  # Exact match to avoid matching E-AC-3
        return 850  # AC-3 Atmos (rare)
    if is_atmos:
        return 900  # Generic Atmos (assume E-AC-3 quality)

    # Lossless codecs (no object-based audio)
    if 'DTS XLL' in format_name or 'DTS-HD MASTER AUDIO' in format_commercial:
        return 700  # DTS-HD MA
    if 'TRUEHD' in format_name or 'MLP FBA' in format_name:
        return 700  # TrueHD
    if format_name == 'FLAC':
        return 650  # FLAC
    if format_name == 'PCM':
        return 650  # PCM

    # High-resolution lossy codecs
    if 'DTS XBR' in format_name or 'DTS-HD HIGH RESOLUTION' in format_commercial:
        return 600  # DTS-HD HRA
    if 'DTS-HD' in format_commercial:
        return 550  # Generic DTS-HD

    # Standard lossy codecs
    if format_name == 'DTS':
        return 500  # DTS
    if 'E-AC-3' in format_name or 'E-AC-3' in format_commercial:
        return 400  # Dolby Digital Plus
    if format_name == 'AC-3':
        return 300  # Dolby Digital
    if format_name == 'AAC':
        return 250  # AAC
    if format_name == 'OPUS':
        return 200  # Opus
    if format_name == 'VORBIS':
        return 150  # Vorbis
    if 'MPEG AUDIO' in format_name:
        return 100  # MP3

    # Unknown or other formats
    return 0


def get_best_audio_track(tracks):
    """
    Get the best audio track from a list, prioritizing codec quality over channel count.

    Selection criteria (in order):
    1. Codec quality (lossless > high-res lossy > standard lossy)
    2. Channel count (7.1 > 5.1 > stereo)

    Args:
        tracks: List of MediaInfo audio tracks

    Returns:
        The best track, or None if list is empty
    """
    if not tracks:
        return None

    # Sort by quality score (descending), then by channel count (descending)
    return max(tracks, key=lambda t: (
        get_codec_quality_score(t),
        get_channel_count(t)
    ))


def select_preferred_audio_track(tracks):
    """
    Select the best audio track, preferring the configured content language,
    then English, then any language.

    Args:
        tracks: List of MediaInfo audio tracks

    Returns:
        The best track, or None if list is empty
    """
    if not tracks:
        return None

    preferred_lang_codes = config.LANGUAGE_CODE_MAP.get(
        config.CONTENT_LANGUAGE, [config.CONTENT_LANGUAGE.lower()])
    english_lang_codes = config.LANGUAGE_CODE_MAP.get('en', ['eng', 'en', 'english'])

    preferred_tracks = []
    english_tracks = []
    for track in tracks:
        language = (track.get('Language') or '').lower()

        if language in preferred_lang_codes:
            preferred_tracks.append(track)
        if language in english_lang_codes:
            english_tracks.append(track)

    return (
        get_best_audio_track(preferred_tracks) or
        get_best_audio_track(english_tracks) or
        get_best_audio_track(tracks)
    )


def get_audio_bitrate(tracks):
    """Get audio bitrate in kbit/s for the preferred language track from MediaInfo tracks"""
    try:
        # Select best track from preferred language, then English, then all
        selected_track = select_preferred_audio_track(get_audio_tracks(tracks))
        bitrate = _track_bitrate_kbps(selected_track, tracks)
        if bitrate:
            return bitrate

        # Last resort: estimate from overall container bitrate
        overall = parse_mediainfo_int(get_general_track(tracks).get('OverallBitRate'))
        if overall:
            estimated_audio = int(overall * config.AUDIO_BITRATE_FORMAT_ESTIMATE_RATIO / 1000)
            if estimated_audio > 0:
                return estimated_audio
    except Exception as e:
        print(f"Error getting audio bitrate: {e}")
    return None


def get_audio_codec(tracks):
    """Get audio codec with detailed profile info, preferring configured language tracks"""
    audio_tracks = get_audio_tracks(tracks)
    if audio_tracks:
        # Select best track from preferred language, then English, then all
        selected_track = select_preferred_audio_track(audio_tracks)

        if selected_track:
            # Extract format information from MediaInfo
            format_commercial = selected_track.get(
                'Format_Commercial_IfAny', '')
            format_name = selected_track.get('Format', '')
            format_profile = selected_track.get('Format_Profile', '')
            format_additional = selected_track.get(
                'Format_AdditionalFeatures', '')
            title = selected_track.get('Title', '')

            # Get channel format string
            channel_str = get_channel_format(get_channel_count(selected_track))
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

    return "Unknown"


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

    is_iso = os.path.splitext(file_path)[1].lower() == '.iso'

    # Run hdrprobe once and reuse the report for HDR detection and, for disc
    # images, as the source of the main-feature video metadata. For an .iso
    # hdrprobe reads the disc playlists, picks the main feature (the largest
    # main movie .m2ts) and reports on it directly.
    hdr_report = run_hdrprobe(file_path)
    hdr_info = detect_hdr_format(file_path, hdr_report)

    iso_sample_path = None
    try:
        if is_iso:
            main_clip = get_hdrprobe_main_clip(hdr_report)
            if main_clip:
                print(f"  [ISO] Main feature clip selected: {main_clip}")
            # MediaInfo's Blu-ray/ISO handling is unreliable, so pull a sample
            # of the main-feature .m2ts out of the image and analyze that.
            iso_sample_path = extract_iso_m2ts_sample(file_path, main_clip)

        # Get container/track metadata with a single MediaInfo call, run
        # against the extracted sample for disc images (falls back to the
        # image itself if the sample could not be produced).
        media_source = iso_sample_path or file_path
        tracks = get_media_info(media_source)

        resolution = get_video_resolution(tracks)
        if resolution == "Unknown":
            resolution = get_hdrprobe_resolution(hdr_report)
        audio_codec = get_audio_codec(tracks)
        audio_bitrate = get_audio_bitrate(tracks)

        if is_iso:
            # The sample is only a prefix of the clip, so its duration and
            # overall bitrate are not representative - take those from
            # hdrprobe, which measured the whole main feature.
            duration = get_hdrprobe_duration(hdr_report) or get_video_duration(tracks)
            video_bitrate = get_hdrprobe_video_bitrate(hdr_report) or get_video_bitrate(tracks)
        else:
            duration = get_video_duration(tracks) or get_hdrprobe_duration(hdr_report)
            video_bitrate = get_video_bitrate(tracks) or get_hdrprobe_video_bitrate(hdr_report)
    finally:
        if iso_sample_path:
            try:
                os.remove(iso_sample_path)
            except OSError:
                pass

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
