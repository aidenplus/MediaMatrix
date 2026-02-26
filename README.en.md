# MediaMatrix

[中文](./README.md) | English

![version](https://img.shields.io/badge/version-1.0.0-blue) ![license](https://img.shields.io/badge/license-MIT-green) ![tests](https://img.shields.io/badge/tests-115%20passed-brightgreen) ![python](https://img.shields.io/badge/python-3.10+-blue) ![docker](https://img.shields.io/badge/docker-ready-blue)

```
██╗    ██╗                      ██╗    ██╗
███╗  ███║           _ _        ███╗  ███║         _       _
████╗████║    ___ __| (_)__ _   ████╗████║    __ _| |_ _ _(_)_ __
██╔████╔██║  / -_) _` | / _` |  ██╔████╔██║  / _` |  _| '_| \ \ /
██║╚██╔╝██║  \___\__,_|_\__,_|  ██║╚██╔╝██║  \__,_|\__|_| |_/_\_\
██║ ╚═╝ ██║                     ██║ ╚═╝ ██║
╚═╝     ╚═╝                     ╚═╝     ╚═╝
```

Automated media scraping tool. Scans local video files, fetches metadata, and generates NFO files and cover images compatible with Infuse / Plex.

## Features

- Real-time directory monitoring — new files trigger scraping automatically
- Full scan on startup to process existing media files
- Generates Kodi-standard NFO files (movies & TV shows)
- Auto-downloads poster.jpg, fanart.jpg, logo.png
- Two scraping modes: `missing_only` / `overwrite`
- `auto_organize`: moves files into `Movie Name (Year)/` subdirectories after scraping
- Multi-provider support with automatic fallback: TMDB → TVDb → OMDb
- Plugin system: supports `.py` source plugins and Cython-compiled `.so` binary plugins
- REST API: manually trigger scans and query task status

## Quick Start

### Step 1: Prepare config file

```bash
git clone https://github.com/aidenplus/MediaMatrix.git
cd MediaMatrix
cp config/settings.example.yaml config/settings.yaml
```

Edit `config/settings.yaml` and fill in at least these two fields:

**1. TMDB API Key (required)**

Apply at [https://www.themoviedb.org/settings/api](https://www.themoviedb.org/settings/api) (free), then set:

```yaml
providers:
  tmdb:
    api_key: "your_api_key"
```

**2. Media library paths (optional)**

Use container paths for Docker (see below), or local paths for native runs:

```yaml
media:
  paths:
    - /media/movies
    - /media/tv
```

---

### Docker (recommended)

#### Set media library paths (replace with your actual paths)

```bash
export MOVIES_PATH=/path/to/movies
export TV_PATH=/path/to/tv
```

Or create a `.env` file in the project root (recommended):

```env
MOVIES_PATH=/path/to/movies
TV_PATH=/path/to/tv
TZ=Asia/Shanghai
```

Then start:

```bash
docker compose up -d
```

#### Update to latest version

```bash
cd MediaMatrix
git pull
docker compose up -d --build
```

### Local

```bash
git clone https://github.com/aidenplus/MediaMatrix.git
cd MediaMatrix
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

## Configuration

| Field | Description |
|-------|-------------|
| `media.paths` | Media library root directories, supports multiple |
| `media.scrape_mode` | `missing_only` (recommended) or `overwrite` |
| `media.auto_organize` | Auto-organize into subdirectories, default `false` |
| `providers.tmdb.api_key` | [TMDB API Key](https://www.themoviedb.org/settings/api), required |
| `providers.tmdb.language` | Metadata language, default `zh-CN` |
| `providers.tvdb.api_key` | [TVDb API Key](https://thetvdb.com/api-information), optional, fallback for TV shows |
| `providers.tvdb.language` | TVDb metadata language, default `zho` |
| `providers.omdb.api_key` | [OMDb API Key](https://www.omdbapi.com/apikey.aspx), optional, final fallback (English only) |
| `concurrency.max_requests` | Max concurrent API requests, default `3` |

## API

See [docs/api.md](docs/api.md) for full documentation.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/status` | Queue and worker status |
| `POST` | `/api/scan` | Trigger scan manually, body: `{"paths": ["/path/to/dir"]}` |
| `GET` | `/api/tasks` | Query task history |

## Plugin Development

Extend `BasePlugin` and implement the hooks you need:

```python
from core.plugin_engine import BasePlugin

class MyPlugin(BasePlugin):
    name = "my_plugin"
    version = "1.0.0"

    def on_init(self, config: dict): ...
    def after_scraped(self, media_item: dict): ...
    def on_error(self, error: Exception, media_item: dict): ...
```

Drop `.py` or compiled `.so` files into the `plugins/` directory — they load automatically on restart.

## Development

```bash
pytest          # run all tests
```

## License

MIT
