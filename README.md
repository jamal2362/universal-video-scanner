# 🎟️ Universal Video Scanner

Universal Video Scanner with Web Interface - Automatic detection of HDR formats including Dolby Vision enhancement layers in video files.

## Features ✨

- **Automatic Scanning**: Watchdog-based detection of new media files
- **All HDR Formats**: SDR, HDR10, HDR10+, HLG, and Dolby Vision (all profiles)
- **Dolby Vision Analysis**: Detection of MEL (Minimum Enhancement Layer) and FEL (Full Enhancement Layer) for all Dolby Vision profiles
- **Web Interface**: Modern dark-theme dashboard on port 2367
- **hdrprobe Integration**: Complete HDR metadata and RPU analysis including enhancement layer detection
- **Docker-based**: Simple deployment with Docker Compose
- **Manual Scan**: Fallback button for on-demand scanning

## Software on Docker Hub 🐳

The software is also available on [Docker Hub](https://hub.docker.com/r/u3known/universal-video-scanner/):

<a href="https://hub.docker.com/r/u3known/universal-video-scanner/" target="_blank">
  <img src="https://github.com/user-attachments/assets/5f58e083-eac7-4eab-84c7-bc75b204f246"
       alt="Docker Hub"
       width="250">
</a>

## Quick Start 🚀

### Prerequisites

- Docker
- Docker Compose

### Installation

1. Clone the repository:
```bash
git clone https://github.com/jamal2362/universal-video-scanner.git
cd universal-video-scanner
```

2. Create media directory:
```bash
mkdir -p media
```

3. Start container:
```bash
docker-compose up -d
```

4. Open web interface:
```
http://localhost:2367
```

## Usage 📖

### Adding Media

Copy your video files to the `media/` directory:

```bash
cp /path/to/video.mkv ./media/
```

The scanner automatically detects new files and analyzes them in the background.

### Supported Formats

- MKV (`.mkv`)
- MP4 (`.mp4`)
- M4V (`.m4v`)
- Transport Stream (`.ts`)
- BDAV Transport Stream (`.m2ts`)
- HEVC Raw (`.hevc`)
- Blu-ray Disc Image (`.iso`)

> **Blu-ray disc images (`.iso`):** Decrypted disc images are supported.
> hdrprobe reads the disc's playlists, automatically picks the main feature
> (usually the largest main-movie `.m2ts`) and analyzes it as if the stream
> file had been probed directly. Encrypted images are detected and rejected.
> To read the audio/video tracks reliably, a minimal BDMV structure is
> reconstructed for the main feature - the playlist (`.mpls`) and clip info
> (`.clpi`) plus a short sample of the main-feature `.m2ts` - and analyzed
> with MediaInfo (via `7z`), no need to extract or mount the full
> multi-gigabyte file. Because the audio languages live in the playlist,
> `CONTENT_LANGUAGE` is honored for track selection just like for regular
> files.
>
> **Performance:** hdrprobe reads the image in place (memory-mapped, only the
> bytes it needs), and MediaInfo only needs the stream headers, so just a
> small prefix of the main feature is sampled - configurable via
> `ISO_SAMPLE_SIZE_MB` (default `16`). Point `TMPDIR` at a tmpfs (e.g.
> `/dev/shm`) to keep that sample in RAM and avoid disk writes entirely.

### Manual Scan

If automatic detection missed a file:

1. Open the web interface
2. Click "🔍 Scan unscanned media"
3. Wait for completion message

## Web Interface 🖥️

The dashboard displays the following information:

| Column | Description |
|--------|-------------|
| **Filename** | Name of the media file |
| **HDR Format** | Detected HDR format (SDR, HDR10, HDR10+, HLG, Dolby Vision with profile) |
| **Resolution** | Video resolution (e.g. 3840x2160) |
| **Audio Codec** | Audio codec information (e.g. Dolby TrueHD Atmos) |

### Features

- 📊 Tabular overview of all scanned media
- 🌙 Dark theme for comfortable viewing
- 🔄 Auto-refresh every 10 seconds
- ⚡ Live status during scanning

## Technical Details 🔧

### Architecture

```
DoVi-Detector/
├── app.py              # Flask application with scanner logic
├── Dockerfile          # Container definition
├── docker-compose.yml  # Deployment configuration
├── requirements.txt    # Python dependencies
├── media/             # Media directory (volume)
└── data/              # Database directory (volume)
    ├── scanned_files.json  # Video scan results
    ├── posters/           # Cached poster images
    ├── static/            # Static files (CSS, JS, fonts, locales)
    └── templates/         # HTML templates
```

### Scanner Workflow

1. **Watchdog** monitors `/media` for new files
2. **hdrprobe** analyzes the video and detects SDR, HDR10, HDR10+, HLG, and Dolby Vision (profile, EL type, CM version)
3. **MediaInfo** extracts resolution, duration, audio codec, and bitrate information
4. **Results** are saved to JSON database

### Static Files and Templates

The application intelligently manages static files and templates with version tracking:

- **First run**: Automatically copies `static/` and `templates/` directories to `./data/`
- **Container restarts**: Your customizations are **preserved** (files are not overwritten)
- **Docker updates**: New versions are automatically deployed when the container image is updated

**File Locations:**
- **Host system**: `./data/static/` and `./data/templates/`
- **Inside container**: `/app/data/static/` and `/app/data/templates/`

**How it works:**
1. On first startup, files are copied from the container to `./data/`
2. You can customize any files (CSS, JS, HTML, translations)
3. On restart, your customizations are **preserved**
4. When you update the Docker image (`docker-compose pull`), the app detects the change and updates the files
5. After an update, you can make new customizations that will again persist across restarts

**Access Rights:**
- All copied files and directories are **writable** by user and group
- You can modify any file without special permissions
- Changes take effect after restarting the container

**Example customizations:**
```bash
# Edit CSS styles
nano ./data/static/css/style.css

# Modify translations
nano ./data/static/locale/en.json

# Customize HTML template
nano ./data/templates/index.html

# Restart container to apply changes (customizations preserved)
docker-compose restart

# Update Docker image (files will be updated to new version)
docker-compose pull
docker-compose up -d
```

### Volumes

- `./media:/media` - Media directory
- `./data:/app/data` - Persistent database, cached posters, static files, and templates

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `FILE_WRITE_DELAY` | `5` | Interval in seconds between file size checks - new files are scanned once their size stops changing |
| `AUTO_REFRESH_INTERVAL` | `10` | Auto-refresh interval of web UI in seconds |
| `ISO_SAMPLE_SIZE_MB` | `100` | Size in MB of the main-feature `.m2ts` sample extracted from Blu-ray disc images (`.iso`) for MediaInfo analysis |
| `TMDB_API_KEY` | `` | TMDB API key for fetching movie posters (optional) |
| `FANART_API_KEY` | `` | Fanart.tv API key for fetching thumb posters (optional) |
| `IMAGE_SOURCE` | `tmdb` | Image source selection: `tmdb` (default) or `fanart` |
| `CONTENT_LANGUAGE` | `en` | Preferred content language (ISO 639-1 code) for TMDB/Fanart.tv content and audio track selection |

### Content Language Configuration

The `CONTENT_LANGUAGE` environment variable controls:
1. **TMDB/Fanart.tv Content**: Language for movie titles, descriptions, and posters
2. **Audio Track Selection**: Preferred audio track language

**Supported Language Codes** (ISO 639-1):
- `en` - English (default)
- `de` - German
- `ru` - Russian
- `bg` - Bulgarian
- `fr` - French
- `es` - Spanish
- `it` - Italian
- `pt` - Portuguese
- `ja` - Japanese
- `ko` - Korean
- `zh` - Chinese
- `nl` - Dutch
- `pl` - Polish
- `sv` - Swedish
- `no` - Norwegian
- `da` - Danish
- `fi` - Finnish
- `tr` - Turkish
- `ar` - Arabic
- `he` - Hebrew
- `hi` - Hindi
- `th` - Thai
- `cs` - Czech
- `hu` - Hungarian
- `ro` - Romanian
- `el` - Greek
- `uk` - Ukrainian

**Fallback Behavior**:
- TMDB queries: If content is not available in the configured language, it falls back to English (`en`)
- Audio tracks: Prefers configured language → English (`eng`) → first available track

**Example Configuration**:

```yaml
environment:
  - CONTENT_LANGUAGE=ru  # Russian for TMDB content + preferred audio track
```

```yaml
environment:
  - CONTENT_LANGUAGE=de  # German
```

```yaml
environment:
  - CONTENT_LANGUAGE=bg  # Bulgarian
```

### TMDB API Integration (Optional)

To display movie posters instead of filenames in the web interface:

1. Get a free API key from [TMDB](https://www.themoviedb.org/settings/api)
2. Add it to your `docker-compose.yml`:

```yaml
environment:
  - TMDB_API_KEY=your_api_key_here
```

Or create a `.env` file in the project root:

```
TMDB_API_KEY=your_api_key_here
```

**Filename Pattern for TMDB ID:**
- Include `{tmdb-12345}` in your filename (e.g., `Movie Name {tmdb-12345}.mkv`)
- If no TMDB ID is found, the app will search TMDB by the extracted movie name

**Poster Caching:**
- Poster images are automatically downloaded and cached in `/app/data/posters/`
- Cached posters are reused on subsequent page loads, reducing bandwidth and load times
- Existing posters are migrated to cache on application startup

**Without TMDB API Key:**
- The app will still work normally, displaying filenames instead of posters

### Fanart.tv API Integration (Optional)

To use Fanart.tv as an alternative image source for thumb posters:

1. Get a free API key from [Fanart.tv](https://fanart.tv/get-an-api-key/)
2. Add it to your `docker-compose.yml`:

```yaml
environment:
  - FANART_API_KEY=your_api_key_here
  - IMAGE_SOURCE=fanart
```

Or create/update a `.env` file in the project root:

```
FANART_API_KEY=your_api_key_here
IMAGE_SOURCE=fanart
```

**Image Source Selection:**
- `IMAGE_SOURCE=tmdb` (default) - Use TMDB for posters
- `IMAGE_SOURCE=fanart` - Use Fanart.tv for thumb posters

**Important Notes:**
- Fanart.tv requires TMDB ID in the filename: `{tmdb-12345}`
- Only movies are supported (TV shows require TVDB ID which is not currently extracted)
- No fallback between sources - only the selected source is used
- Both API keys can be configured, but only the selected source will be used
- Poster images are automatically cached in `/app/data/posters/`

**Without Fanart.tv API Key:**
- The app will still work normally with TMDB or displaying filenames

## Docker Compose Options 🐳

### Standard Configuration

```yaml
docker-compose up -d
```

### View Logs

```bash
docker-compose logs -f
```

### Restart Container

```bash
docker-compose restart
```

### Stop Container

```bash
docker-compose down
```

### Rebuild After Changes

```bash
docker-compose up -d --build
```

## Troubleshooting 🔍

### Container Won't Start

```bash
docker-compose logs dovi-detector
```

### No Files Being Scanned

1. Check if files exist in `media/` directory
2. Use the manual scan button
3. Check logs: `docker-compose logs -f`

### Reset Database

```bash
rm -rf data/scanned_files.json
docker-compose restart
```

## Development 💻

### Local Development Without Docker

```bash
# Install dependencies
pip3 install -r requirements.txt

# mediainfo and hdrprobe must be installed manually

# Start app
python3 app.py
```

### Tests

```bash
# Scan test file
python3 app.py
# Open web interface at http://localhost:2367
```

## Technology Stack 📚

- **Backend**: Python 3 + Flask
- **Scanner**: watchdog (Filesystem Events)
- **Video Analysis**: hdrprobe + MediaInfo
- **Container**: Docker + Docker Compose
- **Frontend**: HTML5 + CSS3 + Vanilla JavaScript

## License 📄

MIT License - see LICENSE file

## Contributing 🤝

Pull requests and issues are welcome!

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a pull request

## Credits 🙏

- [hdrprobe](https://github.com/matthane/hdrprobe) by matthane
- [MediaInfo](https://mediaarea.net/en/MediaInfo)
- [Flask](https://flask.palletsprojects.com/)
- [Watchdog](https://github.com/gorakhargosh/watchdog)

## Support 💬

For questions or issues, please open an issue in the GitHub repository.
