from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class ScanRequest(BaseModel):
    paths: list[str]
    mode: str = "missing_only"  # "missing_only" | "overwrite"


@router.get("/status")
def get_status():
    # TODO: 返回当前任务队列状态
    return {"status": "idle", "queue": 0}


@router.post("/scan")
def trigger_scan(req: ScanRequest):
    # TODO: 将扫描任务推入队列
    return {"message": "scan triggered", "paths": req.paths, "mode": req.mode}


@router.get("/tasks")
def list_tasks():
    # TODO: 从 SQLite 查询任务历史
    return {"tasks": []}
