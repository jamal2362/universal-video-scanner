# Copyright (c) 2026 Jamal2367
# Licensed under the MIT License. See LICENSE file in the project root for full license information.
"""
Video Scanner Service Module
Handles video file analysis, HDR detection, and metadata extraction
"""
import os
import json
import subprocess
import tempfile
from utils.media_utils import get_channel_format, parse_bitrate_string
import config


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
        with tempfile.NamedTemporaryFile(dir=config.TEMP_DIR, suffix='.bin', delete=False) as rpu_tmp:
            rpu_path = rpu_tmp.name

        # Extract RPU metadata
        subprocess.run(
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
                print("  -> HDR10+ detected (fallback text search)")
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


def get_channel_count(track_or_stream, is_mediainfo=True):
    """
    Extract the channel count from a MediaInfo track or ffprobe stream.
    
    Args:
        track_or_stream: MediaInfo track dict or ffprobe stream dict
        is_mediainfo: True if MediaInfo track, False if ffprobe stream
        
    Returns:
        int: Number of channels, or 0 if unable to parse
    """
    if is_mediainfo:
        channels = track_or_stream.get('Channels', '')
        try:
            return int(channels) if channels else 0
        except (ValueError, TypeError):
            return 0
    else:
        return track_or_stream.get('channels', 0) or 0


def get_codec_quality_score(track_or_stream, is_mediainfo=True):
    """
    Get a quality score for an audio codec. Higher score = better quality.
    
    Args:
        track_or_stream: MediaInfo track dict or ffprobe stream dict
        is_mediainfo: True if MediaInfo track, False if ffprobe stream
        
    Returns:
        int: Quality score (higher is better)
    """
    if is_mediainfo:
        format_commercial = track_or_stream.get('Format_Commercial_IfAny', '').upper()
        format_name = track_or_stream.get('Format', '').upper()
        format_additional = track_or_stream.get('Format_AdditionalFeatures', '').upper()
        title = track_or_stream.get('Title', '').upper()
        
        # Check for special formats (object-based audio)
        # Dolby Atmos variants
        if 'DOLBY ATMOS' in format_commercial or 'ATMOS' in format_commercial:
            if 'TRUEHD' in format_name or 'TRUEHD' in format_commercial or 'MLP FBA' in format_name:
                return 1000  # TrueHD Atmos - best Dolby format
            elif 'E-AC-3' in format_name or 'E-AC-3' in format_commercial:
                return 900  # E-AC-3 Atmos
            elif 'AC-3' in format_name:
                return 800  # AC-3 Atmos (rare)
            else:
                return 950  # Generic Atmos
        
        # DTS:X variants
        if ('DTS:X' in format_commercial or 'DTS-X' in format_commercial or
            'DTS XLL X' in format_name or 'XLL X' in format_name or
            'DTS:X' in format_additional or 'DTS:X' in title or 'DTS-X' in title):
            return 950  # DTS:X - comparable to Atmos
        
        # Lossless codecs
        if 'DTS XLL' in format_name or 'DTS-HD MASTER AUDIO' in format_commercial:
            return 700  # DTS-HD MA - lossless
        if 'TRUEHD' in format_name or 'MLP FBA' in format_name:
            return 700  # TrueHD - lossless
        if format_name == 'FLAC':
            return 650  # FLAC - lossless
        if format_name == 'PCM':
            return 650  # PCM - uncompressed
        
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
    else:
        # ffprobe stream
        codec_name = track_or_stream.get('codec_name', '').lower()
        profile = track_or_stream.get('profile', '').lower()
        tags = track_or_stream.get('tags', {})
        title = tags.get('title', '').lower()
        
        # Check for Atmos
        is_atmos = 'atmos' in title or 'atmos' in profile
        
        # Check for DTS:X
        is_dtsx = 'dts:x' in title or 'dtsx' in title or 'dts-x' in title
        
        # Codec-based scoring
        if codec_name == 'truehd':
            return 1000 if is_atmos else 700
        elif codec_name == 'eac3':
            return 900 if is_atmos else 400
        elif codec_name == 'ac3':
            return 800 if is_atmos else 300
        elif codec_name in ['dts', 'dca']:
            if is_dtsx:
                return 950
            elif 'ma' in profile or 'dts-hd ma' in title or 'dts-hd master audio' in title:
                return 700
            elif 'hra' in profile or 'dts-hd hra' in title or 'dts-hd high resolution' in title:
                return 600
            elif 'hd' in profile or 'dts-hd' in title:
                return 550
            else:
                return 500
        elif codec_name == 'flac':
            return 650
        elif codec_name.startswith('pcm'):
            return 650
        elif codec_name == 'aac':
            return 250
        elif codec_name == 'opus':
            return 200
        elif codec_name == 'vorbis':
            return 150
        elif codec_name == 'mp3':
            return 100
        
        # Unknown codec
        return 0


def get_best_audio_track(tracks, is_mediainfo=True):
    """
    Get the best audio track from a list, prioritizing codec quality over channel count.
    
    Selection criteria (in order):
    1. Codec quality (lossless > high-res lossy > standard lossy)
    2. Channel count (7.1 > 5.1 > stereo)
    
    Args:
        tracks: List of MediaInfo tracks or ffprobe streams
        is_mediainfo: True if MediaInfo tracks, False if ffprobe streams
        
    Returns:
        The best track/stream, or None if list is empty
    """
    if not tracks:
        return None
    
    # Sort by quality score (descending), then by channel count (descending)
    return max(tracks, key=lambda t: (
        get_codec_quality_score(t, is_mediainfo=is_mediainfo),
        get_channel_count(t, is_mediainfo=is_mediainfo)
    ))


def get_audio_bitrate(video_file):
    """Get audio bitrate in kbit/s for the preferred language track using ffprobe with multiple fallback mechanisms"""
    # Get language codes for the configured language and English fallback
    preferred_lang_codes = config.LANGUAGE_CODE_MAP.get(config.CONTENT_LANGUAGE, [config.CONTENT_LANGUAGE.lower()])
    english_lang_codes = config.LANGUAGE_CODE_MAP.get('en', ['eng', 'en', 'english'])

    try:
        # Primary + Fallback 1: Try to get BPS from stream tags (MKV) and bit_rate field (MP4)
        cmd = [
            'ffprobe',
            '-v',
            'error',
            '-select_streams',
            'a',
            '-show_entries',
            'stream=index,bit_rate,channels:stream_tags=language,BPS',
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
                # Collect streams by language preference
                preferred_streams = []
                english_streams = []
                all_streams = []

                for stream in data['streams']:
                    tags = stream.get('tags', {})
                    language = tags.get('language', '').lower()
                    all_streams.append(stream)

                    if language in preferred_lang_codes:
                        preferred_streams.append(stream)
                    if language in english_lang_codes:
                        english_streams.append(stream)

                # Select stream with highest channel count from preferred language, then English, then all
                selected_stream = (
                    get_best_audio_track(preferred_streams, is_mediainfo=False) or 
                    get_best_audio_track(english_streams, is_mediainfo=False) or 
                    get_best_audio_track(all_streams, is_mediainfo=False)
                )

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
                    estimated_audio = int(int(format_bitrate) * config.AUDIO_BITRATE_FORMAT_ESTIMATE_RATIO / 1000)
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
                    # Collect tracks by language preference
                    preferred_tracks = []
                    english_tracks = []
                    all_tracks = []

                    for track in audio_tracks:
                        language = track.get('Language', '').lower()
                        all_tracks.append(track)

                        if language in preferred_lang_codes:
                            preferred_tracks.append(track)
                        if language in english_lang_codes:
                            english_tracks.append(track)

                    # Select track with highest channel count from preferred language, then English, then all
                    selected_track = (
                        get_best_audio_track(preferred_tracks, is_mediainfo=True) or 
                        get_best_audio_track(english_tracks, is_mediainfo=True) or 
                        get_best_audio_track(all_tracks, is_mediainfo=True)
                    )

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
    preferred_lang_codes = config.LANGUAGE_CODE_MAP.get(config.CONTENT_LANGUAGE, [config.CONTENT_LANGUAGE.lower()])
    english_lang_codes = config.LANGUAGE_CODE_MAP.get('en', ['eng', 'en', 'english'])

    # Try MediaInfo first for better format detection (especially Atmos and
    # DTS:X)
    audio_tracks = get_audio_info_mediainfo(video_file)
    if audio_tracks:
        # Collect tracks by language preference
        preferred_tracks = []
        english_tracks = []
        all_tracks = []

        for track in audio_tracks:
            language = track.get('Language', '').lower()
            all_tracks.append(track)

            if language in preferred_lang_codes:
                preferred_tracks.append(track)
            if language in english_lang_codes:
                english_tracks.append(track)

        # Select track with highest channel count from preferred language, then English, then all
        selected_track = (
            get_best_audio_track(preferred_tracks, is_mediainfo=True) or 
            get_best_audio_track(english_tracks, is_mediainfo=True) or 
            get_best_audio_track(all_tracks, is_mediainfo=True)
        )

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
                # Collect streams by language preference
                preferred_streams = []
                english_streams = []
                all_streams = []

                for stream in data['streams']:
                    tags = stream.get('tags', {})
                    language = tags.get('language', '').lower()
                    all_streams.append(stream)

                    if language in preferred_lang_codes:
                        preferred_streams.append(stream)
                    if language in english_lang_codes:
                        english_streams.append(stream)

                # Select stream with highest channel count from preferred language, then English, then all
                selected_stream = (
                    get_best_audio_track(preferred_streams, is_mediainfo=False) or 
                    get_best_audio_track(english_streams, is_mediainfo=False) or 
                    get_best_audio_track(all_streams, is_mediainfo=False)
                )

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
        'file_size': file_size
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
