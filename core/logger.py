import logging
import logging.handlers
from pathlib import Path


def setup_logging(level: str = "INFO", log_file: str = "logs/mediamatrix.log") -> None:
    """
    初始化全局日志配置，应在应用启动时调用一次。
    - 控制台：INFO 级别，简洁格式
    - 文件：DEBUG 级别，完整格式，按大小滚动（10MB x 3）
    """
    root = logging.getLogger()

    # 避免重复注册（uvicorn reload 或多次调用时）
    if root.handlers:
        return

    numeric_level = getattr(logging, level.upper(), logging.INFO)
    root.setLevel(logging.DEBUG)

    # 控制台 handler
    console = logging.StreamHandler()
    console.setLevel(numeric_level)
    console.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    ))

    # 文件 handler（滚动，单文件 10MB，保留 3 个）
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.handlers.RotatingFileHandler(
        str(log_path),
        maxBytes=10 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))

    root.addHandler(console)
    root.addHandler(file_handler)

    # 抑制 uvicorn/httpx 等第三方库的 DEBUG 日志，避免刷屏
    for noisy in ("uvicorn.access", "httpx", "httpcore", "fsevents", "watchdog"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
