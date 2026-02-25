from fastapi import APIRouter, Request
from pydantic import BaseModel
from pathlib import Path
from core.task_store import list_tasks

router = APIRouter()


class ScanRequest(BaseModel):
    paths: list[str]
    mode: str = "missing_only"  # "missing_only" | "overwrite"


@router.get("/status")
def get_status(request: Request):
    """返回当前任务队列状态"""
    tq = request.app.state.task_queue  # type: ignore[attr-defined]
    return {
        "status": "running" if tq.is_running else "idle",
        "queue": tq.queue_size,
    }


@router.post("/scan")
async def trigger_scan(req: ScanRequest, request: Request):
    """
    遍历指定路径下的媒体文件，批量推入任务队列。
    返回成功入队的 task_id 列表。
    """
    tq = request.app.state.task_queue  # type: ignore[attr-defined]
    task_ids = []
    video_extensions = tq._config.video_extensions

    for scan_path in req.paths:
        p = Path(scan_path)
        # 单个文件直接入队
        if p.is_file():
            task_id = tq.enqueue(str(p))
            if task_id:
                task_ids.append(task_id)
        # 目录则递归遍历
        elif p.is_dir():
            for file in p.rglob("*"):
                if file.is_file() and file.suffix.lower() in video_extensions:
                    task_id = tq.enqueue(str(file))
                    if task_id:
                        task_ids.append(task_id)

    return {"enqueued": len(task_ids), "task_ids": task_ids}


@router.get("/tasks")
def list_task_history(limit: int = 50):
    """查询最近的任务历史记录"""
    return {"tasks": list_tasks(limit=limit)}
