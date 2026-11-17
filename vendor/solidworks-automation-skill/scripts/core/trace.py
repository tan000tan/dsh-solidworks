"""@brief Execution Trace adapter —— 复用现有 ``queue/events/`` JSONL 事件体系。

本模块**不**建立独立 Trace 存储，不新增 runs/ traces/ 目录，也不启动任何服务。
它把 ``queue/events/{safe_id}.jsonl`` 的追加式 JSONL 事件格式扩展出统一的
``run_id / trace_id / step_id / parent_step_id`` 维度：

- 职责：**执行过程历史**（Trace）。
- 与 Artifact Ledger（最终交付物事实）职责分离，禁止重叠。
- 采用 additive schema：新增字段全部可选，旧事件消费者读取 ``type/at/message/data``
  仍正常工作。

安全约束：
- append-only；
- 单行一次写入 + 追加模式 + flush，保证安全追加；
- 不记录 API Key / 完整 Prompt / 秘密信息（``redact`` 按敏感 key 兜底脱敏）；
- 路径信息由调用方以摘要形式传入，本模块不主动泄露完整私人路径。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping

from .state import now_iso

#: 规范化 Trace 事件词汇表。emit 不强制限制，仅用于文档与测试基线。
TRACE_EVENT_TYPES = frozenset(
    {
        "run.created",
        "run.started",
        "step.started",
        "tool.called",
        "tool.succeeded",
        "tool.failed",
        "verification.started",
        "verification.passed",
        "verification.failed",
        "recovery.retry",
        "recovery.backend_fallback",
        "capability.gap",
        "run.blocked",
        "run.failed",
        "run.completed",
    }
)

#: 与 queue_worker.event_path_for 相同的安全 ID 规则，避免引入新的事件文件命名。
_SAFE_ID_CHARS = re.compile(r"[^A-Za-z0-9_-]")
_SENSITIVE_KEY = re.compile(
    r"prompt|api[_-]?key|token|secret|password|credential|authorization", re.IGNORECASE
)

#: 追加式事件中的可选 additive 字段（全部可选，向后兼容）。
_OPTIONAL_FIELDS = (
    "run_id",
    "trace_id",
    "step_id",
    "parent_step_id",
    "capability_id",
    "backend",
    "duration_ms",
    "error_code",
    "retry_count",
    "verification_status",
)


def sanitize_id(value: Any) -> str:
    """@brief 返回适合作为事件文件名的安全 ID。"""
    safe = _SAFE_ID_CHARS.sub("", str(value or ""))
    return safe[:96] if safe else "unknown"


def events_dir(queue_dir: str | Path) -> Path:
    """@brief 返回事件目录 ``<queue_dir>/events``，不存在时创建。"""
    directory = Path(queue_dir) / "events"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def trace_path_for(queue_dir: str | Path, key: Any) -> Path:
    """@brief 返回某 Run/Job 的事件文件路径。"""
    return events_dir(queue_dir) / f"{sanitize_id(key)}.jsonl"


def redact(value: Any, key: str = "") -> Any:
    """@brief 递归脱敏：命中敏感 key 的值替换为 ``[redacted]``。"""
    if _SENSITIVE_KEY.search(str(key)):
        return "[redacted]"
    if isinstance(value, Mapping):
        return {str(item_key): redact(item_value, str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [redact(item, key) for item in value]
    return value


def _event_key(event: Mapping[str, Any], key: str | None = None) -> str:
    """@brief 解析事件应写入哪个文件：显式 key > run_id/trace_id/jobId。"""
    if key:
        return str(key)
    for field in ("run_id", "trace_id", "jobId", "job_id"):
        if event.get(field):
            return str(event[field])
    return "unknown"


def append_event(queue_dir: str | Path, event: Mapping[str, Any], *, key: str | None = None) -> Path:
    """@brief 追加一行 JSON 事件到 events/{safe_id}.jsonl，返回文件路径。"""
    path = trace_path_for(queue_dir, _event_key(event, key))
    line = json.dumps(redact(event), ensure_ascii=False)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
        handle.flush()
    return path


def emit(
    queue_dir: str | Path,
    event_type: str,
    *,
    key: str | None = None,
    run_id: str | None = None,
    trace_id: str | None = None,
    step_id: str | None = None,
    parent_step_id: str | None = None,
    capability_id: str | None = None,
    backend: str | None = None,
    duration_ms: int | None = None,
    error_code: str | None = None,
    retry_count: int | None = None,
    verification_status: str | None = None,
    message: str = "",
    data: Mapping[str, Any] | None = None,
    at: str | None = None,
) -> Path:
    """@brief 构建并追加一条 Trace 事件（additive schema）。"""
    event: dict[str, Any] = {
        "type": str(event_type),
        "at": at or now_iso(),
        "message": str(message),
    }
    optional = {
        "run_id": run_id,
        "trace_id": trace_id,
        "step_id": step_id,
        "parent_step_id": parent_step_id,
        "capability_id": capability_id,
        "backend": backend,
        "duration_ms": duration_ms,
        "error_code": error_code,
        "retry_count": retry_count,
        "verification_status": verification_status,
    }
    for name, value in optional.items():
        if value is not None:
            event[name] = value
    if data is not None:
        event["data"] = data
    return append_event(queue_dir, event, key=key)


def read_events(queue_dir: str | Path, key: Any) -> list[dict[str, Any]]:
    """@brief 读取某事件文件，返回全部事件（旧/新 schema 均兼容），损坏行跳过。"""
    path = trace_path_for(queue_dir, key)
    if not path.is_file():
        return []
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                events.append(item)
    return events


__all__ = [
    "TRACE_EVENT_TYPES",
    "append_event",
    "emit",
    "events_dir",
    "read_events",
    "redact",
    "sanitize_id",
    "trace_path_for",
]
