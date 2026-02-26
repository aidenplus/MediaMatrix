# MediaMatrix

自动化媒体刮削工具。扫描本地影视文件，自动抓取元数据，生成适配 Infuse / Plex 的 NFO 文件和封面图片。

## 功能

- 实时监控媒体目录，新增文件自动触发刮削
- 启动时全量扫描，处理已存在的媒体文件
- 生成符合 Kodi 标准的 NFO（电影 / 剧集）
- 自动下载 poster.jpg、fanart.jpg、logo.png
- 支持 `missing_only` / `overwrite` 两种刮削策略
- `auto_organize`：刮削完成后自动整理为 `电影名 (年份)/` 子目录
- 多数据源支持，按优先级自动降级：TMDB → TVDb → OMDb
- 插件系统：支持 `.py` 源码插件和 Cython 编译的 `.so` 二进制插件
- REST API：手动触发扫描、查询任务状态

## 快速开始

### Docker（推荐）

```bash
# 复制配置文件并填入 TMDB API Key
cp config/settings.example.yaml config/settings.yaml

# 启动（替换媒体库路径）
MEDIA_PATH=/path/to/media PUID=$(id -u) PGID=$(id -g) docker compose up -d
```

容器内媒体路径为 `/media`，在 `settings.yaml` 中配置：

```yaml
media:
  paths:
    - /media/Movies
    - /media/TV Shows
```

### 本地运行

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp config/settings.example.yaml config/settings.yaml
# 编辑 settings.yaml，填入 TMDB API Key 和本地媒体路径

python main.py
```

## 配置

| 字段 | 说明 |
|------|------|
| `media.paths` | 媒体库根目录，支持多个 |
| `media.scrape_mode` | `missing_only`（推荐）或 `overwrite` |
| `media.auto_organize` | 自动整理目录，默认 `false` |
| `providers.tmdb.api_key` | [TMDB API Key](https://www.themoviedb.org/settings/api)，必填 |
| `providers.tmdb.language` | 元数据语言，默认 `zh-CN` |
| `providers.tvdb.api_key` | [TVDb API Key](https://thetvdb.com/api-information)，可选，剧集备用数据源 |
| `providers.tvdb.language` | TVDb 元数据语言，默认 `zho` |
| `providers.omdb.api_key` | [OMDb API Key](https://www.omdbapi.com/apikey.aspx)，可选，最终备用数据源（英文） |
| `concurrency.max_requests` | 最大并发请求数，默认 `3` |

## API

详见 [docs/api.md](docs/api.md)。

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/status` | 队列状态和 worker 运行状态 |
| `POST` | `/api/scan` | 手动触发扫描，body: `{"paths": ["/path/to/dir"]}` |
| `GET` | `/api/tasks` | 查询任务历史记录 |

## 插件开发

继承 `BasePlugin` 并实现所需 Hook：

```python
from core.plugin_engine import BasePlugin

class MyPlugin(BasePlugin):
    name = "my_plugin"
    version = "1.0.0"

    def on_init(self, config: dict): ...
    def after_scraped(self, media_item: dict): ...
    def on_error(self, error: Exception, media_item: dict): ...
```

将 `.py` 或编译后的 `.so` 文件放入 `plugins/` 目录，重启后自动加载。

## 开发

```bash
pytest          # 运行全部测试
```

## License

MIT
