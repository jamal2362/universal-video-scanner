# DoVi-Detector 🎬

Dolby Vision Profile 7 Media Scanner mit Web-Interface - Automatische Erkennung von MEL/FEL Enhancement Layers in Videodateien.

## Features ✨

- **Automatisches Scannen**: Watchdog-basierte Erkennung neuer Mediendateien
- **Dolby Vision Profile 7**: Dedizierte Erkennung von Profile 7 (MEL/FEL)
- **Web-Interface**: Modernes Dark-Theme Dashboard auf Port 2367
- **dovi_tool Integration**: Vollständige RPU-Analyse und Enhancement Layer Erkennung
- **Docker-basiert**: Einfaches Deployment mit Docker Compose
- **Manueller Scan**: Fallback-Button für On-Demand Scanning

## Schnellstart 🚀

### Voraussetzungen

- Docker
- Docker Compose

### Installation

1. Repository klonen:
```bash
git clone https://github.com/U3knOwn/DoVi-Detector.git
cd DoVi-Detector
```

2. Media-Verzeichnis erstellen:
```bash
mkdir -p media
```

3. Container starten:
```bash
docker-compose up -d
```

4. Web-Interface öffnen:
```
http://localhost:2367
```

## Verwendung 📖

### Medien hinzufügen

Kopieren Sie Ihre Videodateien in das `media/` Verzeichnis:

```bash
cp /pfad/zu/video.mkv ./media/
```

Der Scanner erkennt neue Dateien automatisch und analysiert sie im Hintergrund.

### Unterstützte Formate

- MKV (`.mkv`)
- MP4 (`.mp4`)
- M4V (`.m4v`)
- Transport Stream (`.ts`)
- HEVC Raw (`.hevc`)

### Manueller Scan

Falls die automatische Erkennung eine Datei übersehen hat:

1. Öffnen Sie das Web-Interface
2. Klicken Sie auf "🔍 Nicht gescannte Medien scannen"
3. Warten Sie auf die Completion-Meldung

## Web-Interface 🖥️

Das Dashboard zeigt folgende Informationen:

| Spalte | Beschreibung |
|--------|-------------|
| **Dateiname** | Name der Mediendatei |
| **DV Profile** | Dolby Vision Profil (Profile 7) |
| **Enhancement Layer** | MEL (Minimum Enhancement Layer) oder FEL (Full Enhancement Layer) |
| **Auflösung** | Video-Auflösung (z.B. 3840x2160) |
| **RPU Info** | Erste Zeichen der RPU-Analyse |

### Screenshots

Das Interface bietet:
- 📊 Tabellarische Übersicht aller Profile 7 Medien
- 🌙 Dark Theme für angenehme Nutzung
- 🔄 Auto-Refresh alle 60 Sekunden
- ⚡ Live-Status während des Scannens

## Technische Details 🔧

### Architektur

```
DoVi-Detector/
├── app.py              # Flask-Anwendung mit Scanner-Logik
├── Dockerfile          # Container-Definition
├── docker-compose.yml  # Deployment-Konfiguration
├── requirements.txt    # Python-Dependencies
├── media/             # Medien-Verzeichnis (Volume)
└── data/              # Datenbank-Verzeichnis (Volume)
```

### Scanner-Workflow

1. **Watchdog** überwacht `/media` auf neue Dateien
2. **ffmpeg** extrahiert HEVC-Stream aus Container
3. **dovi_tool extract-rpu** extrahiert RPU-Daten
4. **dovi_tool info** analysiert RPU und ermittelt Profil/EL-Typ
5. **Ergebnisse** werden in JSON-Datenbank gespeichert

### Volumes

- `./media:/media` - Medien-Verzeichnis
- `./data:/app/data` - Persistente Datenbank

### Umgebungsvariablen

| Variable | Standard | Beschreibung |
|----------|----------|-------------|
| `MEDIA_PATH` | `/media` | Pfad zum Medien-Verzeichnis |
| `HEVC_EXTRACT_DURATION` | `3` | Anzahl der Sekunden, die vom Video extrahiert werden (erhöhen, wenn RPU-Daten später im Stream erscheinen) |
| `RPU_INFO_MAX_LENGTH` | `500` | Maximale Länge der RPU-Info in der Datenbank |
| `FILE_WRITE_DELAY` | `5` | Wartezeit in Sekunden nach Dateierstellung vor dem Scan |
| `AUTO_REFRESH_INTERVAL` | `60` | Auto-Refresh-Intervall der Web-UI in Sekunden |

## Docker Compose Optionen 🐳

### Standard-Konfiguration

```yaml
docker-compose up -d
```

### Logs anzeigen

```bash
docker-compose logs -f
```

### Container neustarten

```bash
docker-compose restart
```

### Container stoppen

```bash
docker-compose down
```

### Rebuild nach Änderungen

```bash
docker-compose up -d --build
```

## Troubleshooting 🔍

### Container startet nicht

```bash
docker-compose logs dovi-detector
```

### Keine Dateien werden gescannt

1. Prüfen Sie, ob Dateien im `media/` Verzeichnis liegen
2. Verwenden Sie den manuellen Scan-Button
3. Prüfen Sie die Logs: `docker-compose logs -f`

### Port 2367 bereits belegt

Ändern Sie den Port in `docker-compose.yml`:

```yaml
ports:
  - "8080:2367"  # Extern 8080, intern 2367
```

### Datenbank zurücksetzen

```bash
rm -rf data/scanned_files.json
docker-compose restart
```

## Entwicklung 💻

### Lokale Entwicklung ohne Docker

```bash
# Abhängigkeiten installieren
pip3 install -r requirements.txt

# ffmpeg und dovi_tool müssen manuell installiert werden

# App starten
export MEDIA_PATH=/pfad/zum/media
python3 app.py
```

### Tests

```bash
# Testdatei scannen
python3 app.py
# Web-Interface unter http://localhost:2367 öffnen
```

## Technologie-Stack 📚

- **Backend**: Python 3 + Flask
- **Scanner**: watchdog (Filesystem Events)
- **Video-Analyse**: ffmpeg + dovi_tool
- **Container**: Docker + Docker Compose
- **Frontend**: HTML5 + CSS3 + Vanilla JavaScript

## Lizenz 📄

MIT License - siehe LICENSE Datei

## Mitwirken 🤝

Pull Requests und Issues sind willkommen!

1. Fork das Repository
2. Erstelle einen Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit deine Änderungen (`git commit -m 'Add some AmazingFeature'`)
4. Push zum Branch (`git push origin feature/AmazingFeature`)
5. Öffne einen Pull Request

## Credits 🙏

- [dovi_tool](https://github.com/quietvoid/dovi_tool) von quietvoid
- [FFmpeg](https://ffmpeg.org/)
- [Flask](https://flask.palletsprojects.com/)
- [Watchdog](https://github.com/gorakhargosh/watchdog)

## Support 💬

Bei Fragen oder Problemen öffnen Sie bitte ein Issue im GitHub Repository.
