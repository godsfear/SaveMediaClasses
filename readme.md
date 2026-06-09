# SaveMedia

**A convenient graphical interface for yt-dlp + ffmpeg**  
Download videos, playlists, Shorts, music and any other content from YouTube, VK, Rutube, Telegram and dozens of other sites — beautifully, quickly and ad-free.

![SaveMedia](SaveMedia.png)

## ✨ Features

- **Modern, pleasant interface** built with Flet (Python)
- Support for **thousands of sites** via yt-dlp
- Download video, audio, playlists, subtitles
- Automatic yt-dlp and ffmpeg updates
- Dark theme + persistence of settings and window position
- Download history
- Background operation + notifications
- Localization (Russian + English)
- Proxy, cookies, custom yt-dlp arguments
- Thumbnail previews

## 📸 Screenshots

![Main Screen](images/download.png)

![Settings Screen](images/settings.png)

![History Screen](images/history.png)

## 🚀 Quick start

### Installation

1. Download the latest version from [Releases](https://github.com/godsfear/SaveMediaClasses/releases)
2. Extract the archive
3. Run `SaveMedia.exe` (Windows) or `python main.py` (all platforms)

### Or from source

```bash
git clone https://github.com/godsfear/SaveMediaClasses.git
cd SaveMediaClasses

# uv is recommended
uv sync
uv run python main.py
```

## 🛠 Requirements

Python 3.11+
yt-dlp and ffmpeg (installed automatically)

📖 How to use

Paste a link → choose a format → click "Download"
You can add several links at once
In settings: proxy, save folder, language, default quality, etc.

## 🛣️ Roadmap

Settings presets (music / 4K / audiobook, etc.)
Downloads via torrent, metalink, magnet

## 🙏 Acknowledgements

yt-dlp — the foundation of the project

Flet — the UI framework

## 📄 License
MIT License. See the LICENSE file.
