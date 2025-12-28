#!/usr/bin/env python3
import os
import json
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.request
from pathlib import Path
from flask import Flask, render_template, jsonify, request
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Configuration
MEDIA_PATH = os.environ.get('MEDIA_PATH', '/media')
DATA_DIR = '/app/data'
TEMP_DIR = '/app/temp'
DB_FILE = os.path.join(DATA_DIR, 'scanned_files.json')

# Static files configuration
TEMPLATES_DIR = os.path.join(DATA_DIR, 'templates')
STATIC_DIR = os.path.join(DATA_DIR, 'static')
CSS_DIR = os.path.join(STATIC_DIR, 'css')
JS_DIR = os.path.join(STATIC_DIR, 'js')

# GitHub raw URLs for downloading static files
GITHUB_RAW_BASE = 'https://raw.githubusercontent.com/U3knOwn/dovi-detector/main'
GITHUB_FILES = {
    'templates/index.html': os.path.join(TEMPLATES_DIR, 'index.html'),
    'static/css/style.css': os.path.join(CSS_DIR, 'style.css'),
    'static/js/main.js': os.path.join(JS_DIR, 'main.js'),
}

app = Flask(__name__, 
            template_folder=TEMPLATES_DIR,
            static_folder=STATIC_DIR)

# Scanner configuration constants
FILE_WRITE_DELAY = int(os.environ.get('FILE_WRITE_DELAY', '5'))
AUTO_REFRESH_INTERVAL = int(os.environ.get('AUTO_REFRESH_INTERVAL', '60'))

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
            print(f"  [DV] No RPU file created for {os.path.basename(video_file)}")
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
            print(f"  [DV] dovi_tool info failed for {os.path.basename(video_file)}: {stderr}")
            return None

        # Parse output
        output = dovi_info.stdout.decode('utf-8')
        
        # The output format is: first line is summary, rest is JSON
        lines = output.strip().split('\n')
        if len(lines) < 2:
            print(f"  [DV] Unexpected dovi_tool output format for {os.path.basename(video_file)}")
            return None
            
        json_data = '\n'.join(lines[1:])
        metadata = json.loads(json_data)
        
        profile = metadata.get('dovi_profile')
        el_type = metadata.get('el_type', '').upper()
        
        print(f"  [DV] Dolby Vision detected: Profile {profile}, EL Type: {el_type or 'None'}")

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
        print(f"  [DV] Dolby Vision extraction error for {os.path.basename(video_file)}: {e}")
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
            detail = f'Profile {profile}'
            print(f"  -> Dolby Vision {detail}")
            return {
                'format': 'Dolby Vision',
                'profile': profile,
                'el_type': el_type,
                'detail': detail
            }

        # --- Step 2: HDR10+ (dynamic metadata) ---
        cmd = [
            'ffprobe', '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=side_data',
            '-of', 'json',
            video_file
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode == 0:
            try:
                data = json.loads(result.stdout)
                streams = data.get('streams', [])
                if streams:
                    side_data = streams[0].get('side_data_list', [])
                    for sd in side_data:
                        sd_type = sd.get('side_data_type', '').lower()
                        if sd_type in ['hdr10+ metadata', 'hdr dynamic metadata smpte2094-40']:
                            print(f"  -> HDR10+ detected (side_data)")
                            return {
                                'format': 'HDR10+',
                                'detail': 'HDR10+',
                                'profile': 'HDR10+',
                                'el_type': ''
                            }
            except Exception as e:
                print(f"  [HDR] HDR10+ side_data parsing failed: {e}")

        # Fallback: Full stream info text search
        cmd = [
            'ffprobe', '-v', 'error',
            '-select_streams', 'v:0',
            '-show_streams',
            video_file
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode == 0:
            output_lower = result.stdout.lower()
            if any(indicator in output_lower for indicator in ['hdr10+', 'hdr10plus', 'smpte st 2094', 'smpte2094', 'smpte-st-2094']):
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
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode == 0:
            data = json.loads(result.stdout)
            streams = data.get('streams', [])
            if streams:
                stream = streams[0]
                color_transfer = (stream.get('color_transfer') or '').lower()
                color_primaries = (stream.get('color_primaries') or '').lower()

                print(f"  color_transfer: '{color_transfer}'")
                print(f"  color_primaries: '{color_primaries}'")

                # HDR10 uses PQ (SMPTE2084) + BT.2020
                if any(indicator in color_transfer for indicator in ['smpte2084', 'smpte 2084', 'smpte-2084', 'pq']):
                    print(f"  -> HDR10 detected")
                    return {
                        'format': 'HDR10',
                        'detail': 'HDR10',
                        'profile': 'HDR10',
                        'el_type': ''
                    }

                # HLG (Hybrid Log-Gamma)
                if any(indicator in color_transfer for indicator in ['arib-std-b67', 'arib std b67', 'hlg', 'hybrid log-gamma']):
                    print(f"  -> HLG detected")
                    return {
                        'format': 'HLG',
                        'detail': 'HLG (Hybrid Log-Gamma)',
                        'profile': 'HLG',
                        'el_type': ''
                    }

        # --- Step 4: Fallback to SDR ---
        print(f"  -> Fallback to SDR")
        return {
            'format': 'SDR',
            'detail': 'SDR',
            'profile': 'SDR',
            'el_type': ''
        }

    except Exception as e:
        print(f"[HDR] Error detecting HDR format for {os.path.basename(video_file)}: {e}")
        return {
            'format': 'Unknown',
            'detail': 'Unknown',
            'profile': 'Unknown',
            'el_type': ''
        }

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
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
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
                    return "Full HD (1080p)"
                elif width == 1280 and height == 720:
                    return "HD (720p)"
                elif width == 7680 and height == 4320:
                    return "8K (UHD)"
                elif width == 2560 and height == 1440:
                    return "QHD (1440p)"
                elif width == 4096 and height == 2160:
                    return "4K DCI"
                elif width == 1366 and height == 768:
                    return "HD (768p)"
                elif width == 854 and height == 480:
                    return "SD (480p)"
                elif width == 640 and height == 480:
                    return "SD (480p)"
                else:
                    return f"{width}x{height}"
    except Exception as e:
        print(f"Error getting resolution: {e}")
    return "Unknown"

def get_audio_info_mediainfo(video_file):
    """Get audio information using MediaInfo"""
    try:
        cmd = ['mediainfo', '--Output=JSON', video_file]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            data = json.loads(result.stdout)
            if data.get('media') and 'track' in data['media']:
                audio_tracks = [track for track in data['media']['track'] if track.get('@type') == 'Audio']
                if audio_tracks:
                    return audio_tracks
    except Exception as e:
        print(f"Error getting audio info from MediaInfo: {e}")
    return None

def get_audio_codec(video_file):
    """Get audio codec with detailed profile info, preferring German (ger/deu) tracks"""
    # Try MediaInfo first for better format detection (especially Atmos and DTS:X)
    audio_tracks = get_audio_info_mediainfo(video_file)
    if audio_tracks:
        # Try to find German audio track first
        german_track = None
        first_track = None
        
        for track in audio_tracks:
            language = track.get('Language', '').lower()
            
            if first_track is None:
                first_track = track
            
            if language in ['ger', 'deu', 'de', 'german']:
                german_track = track
                break
        
        # Use German track if found, otherwise first track
        selected_track = german_track if german_track else first_track
        
        if selected_track:
            # Extract format information from MediaInfo
            format_commercial = selected_track.get('Format_Commercial_IfAny', '')
            format_name = selected_track.get('Format', '')
            format_profile = selected_track.get('Format_Profile', '')
            title = selected_track.get('Title', '')
            
            # Check for IMAX in title
            is_imax = 'imax' in title.lower()
            
            # Detect formats using MediaInfo's commercial names and format details
            # Dolby Atmos detection
            if 'Dolby Atmos' in format_commercial or 'Atmos' in format_commercial:
                if 'TrueHD' in format_name or 'TrueHD' in format_commercial:
                    return 'Dolby TrueHD (Atmos)'
                elif 'E-AC-3' in format_name or 'E-AC-3' in format_commercial:
                    return 'Dolby Digital Plus (Atmos)'
                elif 'AC-3' in format_name:
                    return 'Dolby Digital (Atmos)'
                else:
                    return 'Dolby Atmos'
            
            # DTS:X detection
            if 'DTS:X' in format_commercial or 'DTS-X' in format_commercial or 'DTS XLL X' in format_name or 'XLL X' in format_name:
                if is_imax:
                    return 'DTS:X (IMAX)'
                return 'DTS:X'
            
            # Standard format detection based on Format field
            if format_name == 'MLP FBA' or 'TrueHD' in format_name:
                return 'Dolby TrueHD'
            elif format_name == 'E-AC-3' or 'E-AC-3' in format_commercial:
                return 'Dolby Digital Plus'
            elif format_name == 'AC-3':
                return 'Dolby Digital'
            elif 'DTS XLL' in format_name or 'DTS-HD Master Audio' in format_commercial:
                return 'DTS-HD MA'
            elif 'DTS XBR' in format_name or 'DTS-HD High Resolution' in format_commercial:
                return 'DTS-HD HRA'
            elif format_name == 'DTS':
                if 'DTS-HD' in format_commercial:
                    return 'DTS-HD'
                return 'DTS'
            elif format_name == 'AAC':
                return 'AAC'
            elif format_name == 'FLAC':
                return 'FLAC'
            elif format_name == 'MPEG Audio':
                if 'Layer 3' in format_profile:
                    return 'MP3'
                return 'MPEG Audio'
            elif format_name == 'Opus':
                return 'Opus'
            elif format_name == 'Vorbis':
                return 'Vorbis'
            elif format_name == 'PCM':
                return 'PCM'
            else:
                # Return the format name if we didn't match any specific pattern
                return format_name if format_name else 'Unknown'
    
    # Fallback to ffprobe if MediaInfo failed
    try:
        cmd = [
            'ffprobe', '-v', 'error',
            '-select_streams', 'a',
            '-show_entries', 'stream=index,codec_name,profile,channels:stream_tags=language,title',
            '-of', 'json',
            video_file
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            data = json.loads(result.stdout)
            if 'streams' in data and len(data['streams']) > 0:
                # Try to find German audio track first
                german_stream = None
                first_stream = None
                
                for stream in data['streams']:
                    tags = stream.get('tags', {})
                    language = tags.get('language', '').lower()
                    
                    if first_stream is None:
                        first_stream = stream
                    
                    if language in ['ger', 'deu', 'de']:
                        german_stream = stream
                        break
                
                # Use German track if found, otherwise first track
                selected_stream = german_stream if german_stream else first_stream
                
                codec_name = selected_stream.get('codec_name', 'Unknown')
                profile = selected_stream.get('profile', '').lower()
                channels = selected_stream.get('channels', 0)
                tags = selected_stream.get('tags', {})
                title = tags.get('title', '').lower()
                
                # Detect Atmos from title or profile
                is_atmos = 'atmos' in title or 'atmos' in profile
                is_imax = 'imax' in title
                
                # Format codec name with detailed profile information
                if codec_name == 'ac3':
                    return 'Dolby Digital'
                elif codec_name == 'eac3':
                    if is_atmos:
                        return 'Dolby Digital Plus (Atmos)'
                    return 'Dolby Digital Plus'
                elif codec_name == 'truehd':
                    if is_atmos:
                        return 'Dolby TrueHD (Atmos)'
                    return 'Dolby TrueHD'
                elif codec_name in ['dts', 'dca']:
                    if 'dts:x' in title or 'dtsx' in title:
                        if is_imax:
                            return 'DTS:X (IMAX)'
                        return 'DTS:X'
                    elif 'ma' in profile or 'dts-hd ma' in title or 'dts-hd master audio' in title:
                        return 'DTS-HD MA'
                    elif 'hra' in profile or 'dts-hd hra' in title or 'dts-hd high resolution' in title:
                        return 'DTS-HD HRA'
                    elif 'hd' in profile or 'dts-hd' in title:
                        return 'DTS-HD'
                    return 'DTS'
                elif codec_name == 'aac':
                    return 'AAC'
                elif codec_name == 'flac':
                    return 'FLAC'
                elif codec_name == 'mp3':
                    return 'MP3'
                elif codec_name == 'opus':
                    return 'Opus'
                elif codec_name == 'vorbis':
                    return 'Vorbis'
                elif codec_name.startswith('pcm'):
                    return 'PCM'
                else:
                    return codec_name.upper()
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

    file_info = {
        'filename': os.path.basename(file_path),
        'path': file_path,
        'hdr_format': hdr_info.get('format', 'Unknown'),
        'hdr_detail': hdr_info.get('detail', 'Unknown'),
        'profile': hdr_info.get('profile'),
        'el_type': hdr_info.get('el_type'),
        'resolution': resolution,
        'audio_codec': audio_codec
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
                         file_count=len(files_list),
                         auto_refresh_interval=AUTO_REFRESH_INTERVAL)

@app.route('/scan', methods=['POST'])
def manual_scan():
    """Endpoint for manual scan trigger"""
    try:
        initial_count = len(scanned_files)
        
        # Scan for new files
        new_files = scan_directory(MEDIA_PATH)
        
        # Scan each new file
        for file_path in new_files:
            try:
                scan_video_file(file_path)
            except Exception as e:
                print(f"Error scanning {file_path}: {e}")
        
        final_count = len(scanned_files)
        new_count = final_count - initial_count
        
        return jsonify({
            'success': True,
            'new_files': new_count,
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
                    relative_path = os.path.relpath(file_path, MEDIA_PATH)
                    is_scanned = file_path in scanned_paths
                    all_files.append({
                        'path': file_path,
                        'name': relative_path,
                        'scanned': is_scanned
                    })
        
        # Sort by name
        all_files.sort(key=lambda x: x['name'])
        
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

def main():
    """Main application entry point"""
    print("=" * 50)
    print("Starting Universal HDR Video Scanner")
    print("=" * 50)
    
    # Check and download static files if needed
    print("Checking static files...")
    if not download_static_files():
        print("Warning: Failed to download some static files")
    
    # Clean up any orphaned temporary files from previous runs
    cleanup_temp_directory()
    
    # Load existing database
    load_database()
    
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
