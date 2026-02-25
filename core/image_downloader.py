from pathlib import Path
from typing import Optional
import httpx


class ImageDownloader:
    """
    媒体图片下载器，负责将 poster、fanart、logo 保存到本地。
    文件命名遵循 Infuse/Plex 识别规范：
    - poster.jpg  海报（竖版封面）
    - fanart.jpg  背景剧照（横版）
    - logo.png    透明台标/片名 Logo
    """

    def __init__(self):
        self._client = httpx.Client(timeout=30)

    def download_poster(self, url: str, output_dir: str) -> Optional[str]:
        """下载海报，保存为 poster.jpg"""
        return self._download(url, Path(output_dir) / "poster.jpg")

    def download_fanart(self, url: str, output_dir: str) -> Optional[str]:
        """下载背景剧照，保存为 fanart.jpg"""
        return self._download(url, Path(output_dir) / "fanart.jpg")

    def download_logo(self, url: str, output_dir: str) -> Optional[str]:
        """下载透明 Logo，保存为 logo.png"""
        return self._download(url, Path(output_dir) / "logo.png")

    def _download(self, url: str, dest: Path) -> Optional[str]:
        """
        执行实际下载，失败时静默返回 None，不影响主流程。
        TODO: 增加重试机制（指数退避）
        TODO: 支持 missing_only 策略（文件已存在时跳过下载）
        """
        try:
            resp = self._client.get(url)
            resp.raise_for_status()
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(resp.content)
            return str(dest)
        except Exception:
            return None

    def close(self):
        """释放 HTTP 连接池，应在应用关闭时调用"""
        self._client.close()
