# API 文档

Base URL: `http://localhost:8000`

---

## GET /api/status

查询当前任务队列状态。

**响应**

```json
{
  "status": "running",
  "queue": 3
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `status` | string | `running` 表示 worker 正在处理，`idle` 表示空闲 |
| `queue` | integer | 当前队列中待处理的任务数 |

---

## POST /api/scan

手动触发刮削，支持传入文件路径或文件夹路径（递归遍历）。

**请求体**

```json
{
  "paths": ["/media/Movies", "/media/TV Shows"],
  "mode": "missing_only"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `paths` | string[] | 是 | 文件或目录路径列表 |
| `mode` | string | 否 | `missing_only`（默认）跳过已有 NFO 的文件；`overwrite` 强制重新刮削所有文件 |

**响应**

```json
{
  "enqueued": 5,
  "task_ids": ["a1b2c3", "d4e5f6"]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `enqueued` | integer | 成功入队的任务数 |
| `task_ids` | string[] | 入队任务的 ID 列表 |

**示例**

```bash
# 刮削指定目录（跳过已有 NFO）
curl -X POST http://localhost:8000/api/scan \
  -H "Content-Type: application/json" \
  -d '{"paths": ["/media/Movies"]}'

# 强制重新刮削
curl -X POST http://localhost:8000/api/scan \
  -H "Content-Type: application/json" \
  -d '{"paths": ["/media/Movies"], "mode": "overwrite"}'
```

---

## GET /api/tasks

查询任务历史记录，按创建时间倒序排列。

**查询参数**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `limit` | integer | 50 | 返回的最大记录数 |

**响应**

```json
{
  "tasks": [
    {
      "task_id": "a1b2c3",
      "file_path": "/media/Movies/Inception (2010)/Inception.mkv",
      "status": "done",
      "created_at": "2026-02-26T03:00:00",
      "error": null
    }
  ]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `task_id` | string | 任务唯一 ID |
| `file_path` | string | 媒体文件绝对路径 |
| `status` | string | `pending` / `running` / `done` / `failed` |
| `created_at` | string | 任务创建时间（ISO 8601） |
| `error` | string \| null | 失败时的错误信息 |

**示例**

```bash
# 查询最近 10 条记录
curl "http://localhost:8000/api/tasks?limit=10"
```
