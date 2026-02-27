"""
core/image_downloader.py 的单元测试
验证 missing_only 策略（文件已存在时跳过）和 overwrite 模式（强制重新下载）。
"""
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from core.image_downloader import ImageDownloader


@pytest.fixture
def downloader():
    dl = ImageDownloader()
    yield dl
    dl.close()


class TestMissingOnlyStrategy:
    def test_skips_existing_poster(self, downloader, tmp_path):
        """poster.jpg 已存在时，overwrite=False 应跳过下载"""
        poster = tmp_path / "poster.jpg"
        poster.write_bytes(b"original")

        with patch.object(downloader._client, "get") as mock_get:
            result = downloader.download_poster("http://example.com/poster.jpg", str(tmp_path), overwrite=False)

        mock_get.assert_not_called()
        assert result == str(poster)
        assert poster.read_bytes() == b"original"  # 内容未被覆盖

    def test_skips_existing_fanart(self, downloader, tmp_path):
        """fanart.jpg 已存在时，overwrite=False 应跳过下载"""
        fanart = tmp_path / "fanart.jpg"
        fanart.write_bytes(b"original")

        with patch.object(downloader._client, "get") as mock_get:
            downloader.download_fanart("http://example.com/fanart.jpg", str(tmp_path), overwrite=False)

        mock_get.assert_not_called()

    def test_skips_existing_logo(self, downloader, tmp_path):
        """logo.png 已存在时，overwrite=False 应跳过下载"""
        logo = tmp_path / "logo.png"
        logo.write_bytes(b"original")

        with patch.object(downloader._client, "get") as mock_get:
            downloader.download_logo("http://example.com/logo.png", str(tmp_path), overwrite=False)

        mock_get.assert_not_called()

    def test_downloads_when_file_missing(self, downloader, tmp_path):
        """文件不存在时，overwrite=False 也应正常下载"""
        mock_resp = MagicMock()
        mock_resp.content = b"image data"
        mock_resp.raise_for_status = MagicMock()

        with patch.object(downloader._client, "get", return_value=mock_resp):
            result = downloader.download_poster("http://example.com/poster.jpg", str(tmp_path), overwrite=False)

        assert result == str(tmp_path / "poster.jpg")
        assert (tmp_path / "poster.jpg").read_bytes() == b"image data"


class TestOverwriteMode:
    def test_overwrites_existing_poster(self, downloader, tmp_path):
        """overwrite=True 时，即使文件已存在也应重新下载并覆盖"""
        poster = tmp_path / "poster.jpg"
        poster.write_bytes(b"old data")

        mock_resp = MagicMock()
        mock_resp.content = b"new data"
        mock_resp.raise_for_status = MagicMock()

        with patch.object(downloader._client, "get", return_value=mock_resp):
            result = downloader.download_poster("http://example.com/poster.jpg", str(tmp_path), overwrite=True)

        assert result == str(poster)
        assert poster.read_bytes() == b"new data"

    def test_default_is_no_overwrite(self, downloader, tmp_path):
        """默认参数应为 overwrite=False"""
        poster = tmp_path / "poster.jpg"
        poster.write_bytes(b"original")

        with patch.object(downloader._client, "get") as mock_get:
            downloader.download_poster("http://example.com/poster.jpg", str(tmp_path))

        mock_get.assert_not_called()


class TestDownloadFailure:
    def test_returns_none_on_http_error(self, downloader, tmp_path):
        """HTTP 请求失败时静默返回 None，不抛异常"""
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = Exception("404")

        with patch.object(downloader._client, "get", return_value=mock_resp):
            result = downloader.download_poster("http://example.com/poster.jpg", str(tmp_path), overwrite=True)

        assert result is None

    def test_returns_none_on_network_error(self, downloader, tmp_path):
        """网络异常时静默返回 None"""
        with patch.object(downloader._client, "get", side_effect=Exception("timeout")):
            result = downloader.download_poster("http://example.com/poster.jpg", str(tmp_path), overwrite=True)

        assert result is None
