# 插件设计规范

## 1. 插件文件夹标准化结构 (Plugin Bundle)

每个插件是一个独立目录，目录名即插件唯一标识：
```text
/plugins
  └── audio_master/                  # 插件目录名，同时作为入口文件名前缀
      ├── audio_master.so            # 核心逻辑入口（二进制）或
      ├── audio_master.py            # 核心逻辑入口（源码）
      ├── manifest.json              # 插件元数据（必须）
      ├── install.sh                 # 依赖安装脚本，用户手动执行
      ├── bin/                       # 平台相关的外部工具
      │   ├── fpcalc-linux-x64       # Linux x86_64
      │   └── fpcalc-linux-arm64     # Linux ARM64（群晖/NAS）
      ├── config_default.yaml        # 默认配置（API Keys 等），插件自行读取
      └── assets/                    # 静态资源（如默认海报占位图）
```

入口文件命名规则：与插件目录同名，扩展名为 `.so`（二进制）或 `.py`（源码）。
主程序按此规则定位入口，无需在 `manifest.json` 中声明 `entry` 字段。

## 2. manifest.json

`manifest.json` 是必须文件，缺失或 `id` 字段为空时主程序会跳过该插件并打印警告。

```json
{
  "id": "com.yourname.audio_master",
  "version": "1.0.2",
  "name": "智能音频刮削器",
  "description": "基于 AcoustID 的音乐识别插件，支持 Plex/Infuse 优化。"
}
```

字段说明：

| 字段 | 必须 | 说明 |
|------|------|------|
| `id` | 是 | 全局唯一标识，建议反向域名格式（`com.yourname.plugin_name`） |
| `version` | 是 | 语义化版本号 |
| `name` | 是 | 展示名称，用于日志输出 |
| `description` | 否 | 插件功能描述 |

## 3. 依赖安装

插件如有额外 Python 依赖，通过 `install.sh` 手动安装，不由主程序自动执行：
```bash
#!/bin/bash
pip install mutagen acoustid
```

用户在部署插件后手动执行一次：
```bash
bash plugins/audio_master/install.sh
```

## 4. 插件配置

主程序不处理插件配置，插件在 `on_init` 中自行读取 `config_default.yaml`：

```python
import yaml
from pathlib import Path

def on_init(self, config: dict) -> None:
    config_path = Path(__file__).parent / "config_default.yaml"
    with open(config_path) as f:
        self._config = yaml.safe_load(f)
    self._api_key = self._config.get("api_key", "")
```

`config` 参数是主程序 `settings.yaml` 的完整内容（`dict`），插件可从中读取全局配置（如代理设置、并发数等），但插件自身的配置应放在 `config_default.yaml` 中独立管理。

## 5. 跨架构兼容性

`bin/` 目录下按平台命名二进制文件，插件代码在运行时通过 `platform.machine()` 自动选择：

| 文件名后缀 | 适用平台 |
|-----------|---------|
| `-linux-x64` | Linux x86_64（标准 Docker） |
| `-linux-arm64` | Linux ARM64（群晖、NAS、树莓派） |

```python
import platform
from pathlib import Path

def _get_fpcalc(self) -> str:
    arch = "arm64" if platform.machine() == "aarch64" else "x64"
    return str(Path(__file__).parent / "bin" / f"fpcalc-linux-{arch}")
```

注意：`.so` 文件中 `__file__` 在极少数情况下可能为 `None`，建议加防御：
```python
base = Path(__file__).parent if __file__ else Path(__spec__.origin).parent
```

## 6. 主程序加载机制

`PluginEngine.load_plugins()` 同时支持单文件和文件夹两种插件格式：

- 单文件：`plugins/my_plugin.py` 或 `plugins/my_plugin.so`
- 文件夹：`plugins/audio_master/audio_master.py` 或 `plugins/audio_master/audio_master.so`

加载顺序：读取 `manifest.json` 校验 `id` → 定位同名入口文件 → 动态加载模块 → 发现并实例化 `BasePlugin` 子类。

加载失败（`manifest.json` 缺失、`id` 为空、入口文件不存在、模块加载异常）时，主程序打印警告并跳过，不影响其他插件和主流程。

**模块隔离**：每个插件以 `plugins.<目录名>` 作为唯一模块名加载，通过 `importlib` 的 `submodule_search_locations` 限定搜索范围，不修改全局 `sys.path`，避免插件间命名冲突。

插件内部模块引用须使用相对导入：
```python
# 正确
from . import utils
from .config import load_config

# 错误（裸导入会在全局命名空间查找，找不到或找错）
import utils
```

## 7. Hook 接口参考

### on_init(config: dict)

系统启动时调用一次，适合做初始化（建立连接、加载模型、读取配置）。

`config` 结构（对应 `settings.yaml`）：
```python
{
    "app": {"host": "0.0.0.0", "port": 8000},
    "media": {"paths": [...], "scrape_mode": "missing_only", ...},
    "providers": {"tmdb": {"api_key": "...", "language": "zh-CN"}, ...},
    "concurrency": {"max_requests": 3},
    ...
}
```

### after_scraped(media_item: dict)

每次刮削成功后触发，适合做后处理（字幕生成、通知推送等）。

`media_item` 字段：
```python
{
    "file_path": "/media/movies/流浪地球.mkv",  # 视频文件绝对路径
    "title": "流浪地球",                         # 刮削到的标题
    "year": 2019,                               # 年份，可能为 None
    "media_type": "movie",                      # "movie" | "tv" | "music"
}
```

### on_error(error: Exception, media_item: dict)

刮削失败时触发，适合做报警（发送通知、写日志等）。

`media_item` 字段：
```python
{
    "file_path": "/media/movies/未知文件.mkv",  # 触发失败的文件路径
}
```

## 8. 完整示例

一个最小可运行的插件，刮削完成后打印通知：

```python
# plugins/hello_plugin/hello_plugin.py
import logging
from pathlib import Path
from core.plugin_engine import BasePlugin

logger = logging.getLogger(__name__)


class HelloPlugin(BasePlugin):
    name = "hello_plugin"
    version = "1.0.0"

    def on_init(self, config: dict) -> None:
        logger.info("[HelloPlugin] 已加载，当前刮削模式: %s", config["media"]["scrape_mode"])

    def after_scraped(self, media_item: dict) -> None:
        logger.info("[HelloPlugin] 刮削完成: %s (%s)", media_item["title"], media_item["year"])

    def on_error(self, error: Exception, media_item: dict) -> None:
        logger.warning("[HelloPlugin] 刮削失败: %s，原因: %s", media_item["file_path"], error)
```

对应的 `manifest.json`：
```json
{
  "id": "com.example.hello_plugin",
  "version": "1.0.0",
  "name": "Hello Plugin",
  "description": "最小示例插件"
}
```
