"""
core/task_store.py 的单元测试
使用内存 SQLite 数据库，通过 monkeypatch 替换 DB_PATH，避免污染真实数据库。
"""
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
import core.task_store as task_store
from core.task_store import ScrapeTask, init_db, insert_task, update_status, list_tasks


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    """每个测试使用独立的临时数据库文件"""
    db_file = tmp_path / "tasks.db"
    monkeypatch.setattr(task_store, "DB_PATH", db_file)
    init_db()
    yield db_file


def _make_task(task_id: str = "abc-123", file_path: str = "/media/test.mp4") -> ScrapeTask:
    return ScrapeTask(
        task_id=task_id,
        file_path=file_path,
        status="pending",
        created_at=datetime.now().isoformat(),
    )


class TestInitDb:
    def test_creates_tasks_table(self, tmp_path, monkeypatch):
        """init_db 应创建 tasks 表"""
        import sqlite3
        db_file = tmp_path / "new.db"
        monkeypatch.setattr(task_store, "DB_PATH", db_file)
        init_db()
        conn = sqlite3.connect(str(db_file))
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        conn.close()
        assert ("tasks",) in tables

    def test_idempotent(self):
        """多次调用 init_db 不应报错"""
        init_db()
        init_db()


class TestInsertTask:
    def test_insert_and_retrieve(self):
        """插入任务后应能通过 list_tasks 查到"""
        task = _make_task()
        insert_task(task)
        rows = list_tasks()
        assert len(rows) == 1
        assert rows[0]["task_id"] == "abc-123"
        assert rows[0]["file_path"] == "/media/test.mp4"
        assert rows[0]["status"] == "pending"

    def test_insert_multiple(self):
        """插入多条任务，list_tasks 应按创建时间倒序返回"""
        insert_task(_make_task("id-1", "/media/a.mp4"))
        insert_task(_make_task("id-2", "/media/b.mp4"))
        rows = list_tasks()
        assert len(rows) == 2
        # 倒序：id-2 在前
        assert rows[0]["task_id"] == "id-2"


class TestUpdateStatus:
    def test_update_to_done(self):
        """更新状态为 done 后应能查到新状态"""
        task = _make_task()
        insert_task(task)
        update_status(task.task_id, "done")
        rows = list_tasks()
        assert rows[0]["status"] == "done"
        assert rows[0]["error"] is None

    def test_update_to_failed_with_error(self):
        """更新为 failed 时应记录错误信息"""
        task = _make_task()
        insert_task(task)
        update_status(task.task_id, "failed", error="未找到匹配元数据")
        rows = list_tasks()
        assert rows[0]["status"] == "failed"
        assert rows[0]["error"] == "未找到匹配元数据"


class TestListTasks:
    def test_limit(self):
        """list_tasks 的 limit 参数应限制返回条数"""
        for i in range(10):
            insert_task(_make_task(f"id-{i:02d}", f"/media/{i}.mp4"))
        rows = list_tasks(limit=3)
        assert len(rows) == 3

    def test_empty_returns_empty_list(self):
        """无任务时返回空列表"""
        assert list_tasks() == []
