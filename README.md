# MediaMatrix

[English](./README.en.md) | 中文

![version](https://img.shields.io/badge/version-1.0.0-blue) ![license](https://img.shields.io/badge/license-MIT-green) ![tests](https://img.shields.io/badge/tests-141%20passed-brightgreen) ![python](https://img.shields.io/badge/python-3.10+-blue) ![docker](https://img.shields.io/badge/docker-ready-blue)

```
██╗    ██╗                      ██╗    ██╗
███╗  ███║           _ _        ███╗  ███║         _       _
████╗████║    ___ __| (_)__ _   ████╗████║    __ _| |_ _ _(_)_ __
██╔████╔██║  / -_) _` | / _` |  ██╔████╔██║  / _` |  _| '_| \ \ /
██║╚██╔╝██║  \___\__,_|_\__,_|  ██║╚██╔╝██║  \__,_|\__|_| |_/_\_\
██║ ╚═╝ ██║                     ██║ ╚═╝ ██║
╚═╝     ╚═╝                     ╚═╝     ╚═╝
```

自动化媒体刮削工具。扫描本地影视文件，自动抓取元数据，生成适配 Infuse / Plex 的 NFO 文件和封面图片。

## 功能

- 实时监控媒体目录，新增文件自动触发刮削
- 启动时全量扫描，处理已存在的媒体文件
- 生成符合 Kodi 标准的 NFO（电影 / 剧集）
- 自动下载 poster.jpg、fanart.jpg、logo.png
- 支持 `missing_only` / `overwrite` 两种刮削策略
- `auto_organize`：刮削完成后自动整理为 `电影名 (年份)/` 子目录
- 多数据源支持，按优先级自动降级：TMDB → TVDb → OMDb → LLM 兜底
- **LLM 兜底刮削**：所有数据源均失败时，调用 LLM 识别冷门内容（推荐使用百度千帆 ERNIE，支持实时联网搜索）
- 插件系统：支持 `.py` 源码插件和 Cython 编译的 `.so` 二进制插件
- REST API：手动触发扫描、查询任务状态

## 快速开始

### 第一步：准备配置文件

```bash
git clone https://github.com/aidenplus/MediaMatrix.git
cd MediaMatrix
cp config/settings.example.yaml config/settings.yaml
```

编辑 `config/settings.yaml`，至少填写以下两项：

**1. TMDB API Key（必填）**

前往 [https://www.themoviedb.org/settings/api](https://www.themoviedb.org/settings/api) 申请（免费），填入：

```yaml
providers:
  tmdb:
    api_key: "你的 API Key"
```

**2. 媒体库路径（可选）**

Docker 用容器内路径（见下方），本地运行用本机实际路径：

```yaml
media:
  paths:
    - /media/movies   # Docker 路径示例
    - /media/tv
```

---

### Docker部署（推荐）

#### 设置宿主机媒体库路径（替换为你的实际路径）

```bash
export MOVIES_PATH=/path/to/movies
export TV_PATH=/path/to/tv
```

也可以在项目根目录创建 `.env` 文件（推荐）：

```env
MOVIES_PATH=/path/to/movies
TV_PATH=/path/to/tv
TZ=Asia/Shanghai
```

然后直接运行：

```bash
docker compose up -d
```

#### 代码更新

```bash
cd MediaMatrix
git pull
docker compose up -d --build
````

### 代码本地运行

```bash
git clone https://github.com/aidenplus/MediaMatrix.git
cd MediaMatrix
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
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
| `providers.llm.api_key` | LLM 兜底数据源 API Key，可选，留空则不启用 |
| `providers.llm.base_url` | LLM 接口地址，兼容任意 OpenAI 格式服务 |
| `providers.llm.model` | 使用的模型名称 |
| `concurrency.max_requests` | 最大并发请求数，默认 `3` |

### LLM 兜底刮削

当 TMDB、TVDb、OMDb 均无法识别某个媒体文件时，MediaMatrix 会将文件名发送给 LLM，由模型生成元数据作为最后兜底。

**推荐使用百度千帆 ERNIE 系列模型**，因为它内置实时百度搜索能力，对中文冷门影视（如老剧、短片、纪录片）的识别效果显著优于纯离线模型。

```yaml
providers:
  llm:
    api_key: "你的千帆 API Key"
    base_url: "https://qianfan.baidubce.com/v2"
    model: "ernie-4.5-turbo-128k"
```

也支持其他兼容 OpenAI 格式的服务：

| 服务 | base_url | 推荐模型 |
|------|----------|---------|
| 百度千帆（推荐）| `https://qianfan.baidubce.com/v2` | `ernie-4.5-turbo-128k` |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| 本地 Ollama | `http://localhost:11434/v1` | `qwen2.5` |

> 注意：LLM 生成的元数据准确性不保证，适合作为冷门内容的兜底方案。`api_key` 留空则不启用此功能。

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
