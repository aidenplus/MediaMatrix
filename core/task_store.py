import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent.parent / "config" / "tasks.db"


@dataclass
class ScrapeTask:
    task_id: str
    file_path: str
    status: str        # pending | running | done | failed
    created_at: str
    error: Optional[str] = None


def init_db() -> None:
    """初始化数据库，创建任务表（幂等）"""
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                task_id    TEXT PRIMARY KEY,
                file_path  TEXT NOT NULL,
                status     TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                error      TEXT
            )
        """)


def insert_task(task: ScrapeTask) -> None:
    """插入一条新任务记录"""
    with _conn() as conn:
        conn.execute(
            "INSERT INTO tasks (task_id, file_path, status, created_at) VALUES (?, ?, ?, ?)",
            (task.task_id, task.file_path, task.status, task.created_at),
        )


def update_status(task_id: str, status: str, error: Optional[str] = None) -> None:
    """更新任务状态，失败时记录错误信息"""
    with _conn() as conn:
        conn.execute(
            "UPDATE tasks SET status = ?, error = ? WHERE task_id = ?",
            (status, error, task_id),
        )


def list_tasks(limit: int = 50) -> list[dict]:
    """查询最近的任务记录，按创建时间倒序"""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT task_id, file_path, status, created_at, error FROM tasks ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [
        {"task_id": r[0], "file_path": r[1], "status": r[2], "created_at": r[3], "error": r[4]}
        for r in rows
    ]


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(str(DB_PATH))
