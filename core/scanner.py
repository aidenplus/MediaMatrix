from pathlib import Path
from typing import Callable
import logging
from watchdog.observers.polling import PollingObserver
from watchdog.events import FileSystemEventHandler, FileSystemEvent

logger = logging.getLogger(__name__)


class _EventHandler(FileSystemEventHandler):
    """
    watchdog 事件处理器，过滤目录事件，只处理文件的新增和移动。
    移动事件（如从下载目录移入媒体库）也视为新文件触发回调。
    """

    def __init__(self, callback: Callable[[str], None], media_extensions: set[str] = None):
        self._callback = callback
        self._media_extensions = media_extensions

    def _should_handle(self, path: str) -> bool:
        if self._media_extensions is None:
            return True
        return Path(path).suffix.lower() in self._media_extensions

    def on_created(self, event: FileSystemEvent):
        if not event.is_directory and self._should_handle(event.src_path):
            logger.debug("检测到新文件: %s", event.src_path)
            self._callback(event.src_path)

    def on_moved(self, event: FileSystemEvent):
        # 文件被移动到监控目录时，以目标路径触发回调
        if not event.is_directory and self._should_handle(event.dest_path):
            logger.debug("检测到移入文件: %s", event.dest_path)
            self._callback(event.dest_path)


class MediaScanner:
    """
    媒体文件扫描器，基于 watchdog 实现实时目录监控。

    使用方式：
    1. add_path() 添加监控目录
    2. scan_existing() 处理已存在的文件（启动时全量扫描）
    3. start() 启动实时监控
    4. stop() 停止监控（应在应用关闭时调用）
    """

    def __init__(self, on_file: Callable[[str], None], media_extensions: set[str] = None, poll_interval: int = 5):
        """
        :param on_file: 发现新文件时的回调函数，参数为文件绝对路径
        :param media_extensions: 需要处理的文件扩展名集合，None 表示不过滤
        :param poll_interval: 轮询间隔（秒），默认 5 秒
        """
        self._on_file = on_file
        self._media_extensions = media_extensions
        self._observer = PollingObserver(timeout=poll_interval)
        self.watch_paths: list[str] = []

    def add_path(self, path: str) -> None:
        """添加一个需要监控的根目录"""
        self.watch_paths.append(path)

    def start(self) -> None:
        """启动 watchdog 观察者，开始监听所有已注册路径"""
        handler = _EventHandler(self._on_file, self._media_extensions)
        for path in self.watch_paths:
            self._observer.schedule(handler, path, recursive=True)
            logger.info("开始监控目录: %s", path)
        self._observer.start()

    def stop(self) -> None:
        """停止监控并等待线程退出，未启动时安全跳过"""
        if self._observer.is_alive():
            self._observer.stop()
            self._observer.join()
            logger.info("文件监控已停止")

    def scan_existing(self) -> list[str]:
        """
        扫描所有监控目录中已存在的媒体文件，返回文件路径列表。
        用于应用启动时的全量刮削（配合 missing_only 策略避免重复处理）。
        """
        files = []
        for path in self.watch_paths:
            for p in Path(path).rglob("*"):
                if p.is_file():
                    if self._media_extensions is None or p.suffix.lower() in self._media_extensions:
                        files.append(str(p))
        return files
