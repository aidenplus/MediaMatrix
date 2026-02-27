"""
core/scanner.py 的单元测试
验证 scan_existing() 的扩展名过滤逻辑。
"""
import pytest
from core.scanner import MediaScanner


@pytest.fixture
def media_dir(tmp_path):
    """创建包含各类文件的测试目录结构"""
    (tmp_path / "movie.mkv").touch()
    (tmp_path / "show.mp4").touch()
    (tmp_path / "movie.nfo").touch()
    (tmp_path / "poster.jpg").touch()
    (tmp_path / "subtitle.srt").touch()
    sub = tmp_path / "subdir"
    sub.mkdir()
    (sub / "episode.mkv").touch()
    (sub / "fanart.jpg").touch()
    return tmp_path


class TestScanExisting:
    def test_filters_by_extensions(self, media_dir):
        """只返回指定扩展名的文件"""
        scanner = MediaScanner(on_file=lambda p: None, media_extensions={".mkv", ".mp4"})
        scanner.add_path(str(media_dir))
        files = scanner.scan_existing()
        suffixes = {f.rsplit(".", 1)[-1] for f in files}
        assert suffixes == {"mkv", "mp4"}

    def test_returns_all_files_when_no_filter(self, media_dir):
        """media_extensions=None 时返回所有文件，不过滤"""
        scanner = MediaScanner(on_file=lambda p: None, media_extensions=None)
        scanner.add_path(str(media_dir))
        files = scanner.scan_existing()
        assert len(files) == 7  # mkv, mp4, nfo, poster.jpg, subtitle.srt, subdir/mkv, subdir/fanart.jpg

    def test_scans_subdirectories_recursively(self, media_dir):
        """应递归扫描子目录"""
        scanner = MediaScanner(on_file=lambda p: None, media_extensions={".mkv"})
        scanner.add_path(str(media_dir))
        files = scanner.scan_existing()
        names = [f.split("/")[-1] for f in files]
        assert "movie.mkv" in names
        assert "episode.mkv" in names

    def test_excludes_non_matching_extensions(self, media_dir):
        """非指定扩展名的文件不应出现在结果中"""
        scanner = MediaScanner(on_file=lambda p: None, media_extensions={".mkv", ".mp4"})
        scanner.add_path(str(media_dir))
        files = scanner.scan_existing()
        names = [f.split("/")[-1] for f in files]
        assert "movie.nfo" not in names
        assert "poster.jpg" not in names
        assert "subtitle.srt" not in names

    def test_multiple_watch_paths(self, tmp_path):
        """多个监控路径都应被扫描"""
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        dir_a.mkdir()
        dir_b.mkdir()
        (dir_a / "film.mkv").touch()
        (dir_b / "show.mp4").touch()

        scanner = MediaScanner(on_file=lambda p: None, media_extensions={".mkv", ".mp4"})
        scanner.add_path(str(dir_a))
        scanner.add_path(str(dir_b))
        files = scanner.scan_existing()
        names = [f.split("/")[-1] for f in files]
        assert "film.mkv" in names
        assert "show.mp4" in names

    def test_empty_directory_returns_empty_list(self, tmp_path):
        """空目录应返回空列表"""
        scanner = MediaScanner(on_file=lambda p: None, media_extensions={".mkv"})
        scanner.add_path(str(tmp_path))
        assert scanner.scan_existing() == []
