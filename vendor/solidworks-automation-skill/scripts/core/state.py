"""@brief Execution Core 轻量执行状态模型。

本模块只定义「可 JSON 序列化、带 schema version、与 CAD Studio Queue Job 解耦」
的运行时状态数据结构，供 Worker / MCP / CLI 复用。它**不**实现完整状态机框架，
只提供最小转换白名单，用于拦截 ``FAILED -> COMPLETED``、``BLOCKED -> COMPLETED``
这类明显非法转换。

状态值统一使用小写（与仓库现有 queue 状态 ``queued/running/passed`` 保持一致）；
``VerificationStatus`` 按 V2 约定使用大写 ``PASS/WARN/FAIL/BLOCKED``。

安全约束：
- 不保存完整 Prompt / API Key / 秘密信息；
- 参数与结果只保存 ``arguments_summary`` / ``result_summary`` 摘要，不保存原文；
- 不建议保存无必要的完整私人绝对路径。
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping

SCHEMA_VERSION = "1.0"


def now_iso() -> str:
    """@brief 返回 UTC 时区 ISO 时间字符串。"""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class RunStatus(str, Enum):
    """@brief 一次 Run 的生命周期状态。"""

    CREATED = "created"
    RUNNING = "running"
    VERIFYING = "verifying"
    RETRYING = "retrying"
    BLOCKED = "blocked"
    FAILED = "failed"
    COMPLETED = "completed"


class StepStatus(str, Enum):
    """@brief 单个 Step 的生命周期状态。"""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    VERIFYING = "verifying"
    RETRYING = "retrying"
    BLOCKED = "blocked"


class VerificationStatus(str, Enum):
    """@brief 验证结论（V2 约定统一使用大写）。"""

    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"


#: 结构化恢复决策的允许取值（Recovery Engine 在后续 Phase 落地，这里只定义数据模型）。
RECOVERY_ACTIONS = frozenset(
    {
        "retry",
        "fallback_backend",
        "replan_required",
        "user_action_required",
        "block",
        "fail",
    }
)


class InvalidStateTransition(ValueError):
    """@brief 非法状态转换。"""


# 最小转换白名单：只拦明显非法转换，不引入复杂 FSM 框架。
_RUN_TRANSITIONS: dict[RunStatus, set[RunStatus]] = {
    RunStatus.CREATED: {RunStatus.RUNNING, RunStatus.BLOCKED, RunStatus.FAILED},
    RunStatus.RUNNING: {
        RunStatus.VERIFYING,
        RunStatus.RETRYING,
        RunStatus.BLOCKED,
        RunStatus.FAILED,
        RunStatus.COMPLETED,
    },
    RunStatus.VERIFYING: {
        RunStatus.COMPLETED,
        RunStatus.RETRYING,
        RunStatus.BLOCKED,
        RunStatus.FAILED,
    },
    RunStatus.RETRYING: {
        RunStatus.RUNNING,
        RunStatus.VERIFYING,
        RunStatus.BLOCKED,
        RunStatus.FAILED,
    },
    RunStatus.BLOCKED: {RunStatus.RUNNING},
    RunStatus.FAILED: {RunStatus.RETRYING},
    RunStatus.COMPLETED: set(),
}

_STEP_TRANSITIONS: dict[StepStatus, set[StepStatus]] = {
    StepStatus.PENDING: {StepStatus.RUNNING, StepStatus.BLOCKED},
    StepStatus.RUNNING: {
        StepStatus.SUCCESS,
        StepStatus.FAILED,
        StepStatus.VERIFYING,
        StepStatus.BLOCKED,
    },
    StepStatus.VERIFYING: {
        StepStatus.SUCCESS,
        StepStatus.FAILED,
        StepStatus.RETRYING,
        StepStatus.BLOCKED,
    },
    StepStatus.RETRYING: {StepStatus.RUNNING, StepStatus.BLOCKED, StepStatus.FAILED},
    StepStatus.BLOCKED: {StepStatus.RUNNING, StepStatus.PENDING},
    StepStatus.SUCCESS: set(),
    StepStatus.FAILED: {StepStatus.RETRYING},
}


def _coerce_enum(enum_cls: type[Enum], value: Any, default: Any = None) -> Any:
    """@brief 宽松地把字符串/枚举归一化为指定枚举成员，未知值返回默认。"""
    if value is None:
        return default
    if isinstance(value, enum_cls):
        return value
    text = str(value)
    for member in enum_cls:
        if member.value.lower() == text.lower():
            return member
    try:
        return enum_cls(text)
    except ValueError:
        return default


def _serialize(value: Any) -> Any:
    """@brief 递归把 Enum 转为 value，生成 JSON 兼容结构。"""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _serialize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(item) for item in value]
    if is_dataclass(value):
        return _serialize(asdict(value))
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def can_transition_run(current: RunStatus | str, target: RunStatus | str) -> bool:
    """@brief 判断 Run 状态转换是否合法。"""
    current = _coerce_enum(RunStatus, current, None)
    target = _coerce_enum(RunStatus, target, None)
    if current is None or target is None:
        return False
    return target in _RUN_TRANSITIONS.get(current, set())


def can_transition_step(current: StepStatus | str, target: StepStatus | str) -> bool:
    """@brief 判断 Step 状态转换是否合法。"""
    current = _coerce_enum(StepStatus, current, None)
    target = _coerce_enum(StepStatus, target, None)
    if current is None or target is None:
        return False
    return target in _STEP_TRANSITIONS.get(current, set())


def ensure_run_transition(current: RunStatus | str, target: RunStatus | str) -> None:
    """@brief 校验 Run 状态转换，非法时抛出 InvalidStateTransition。"""
    if not can_transition_run(current, target):
        cur = _coerce_enum(RunStatus, current, current)
        tgt = _coerce_enum(RunStatus, target, target)
        raise InvalidStateTransition(
            f"非法 Run 状态转换: {getattr(cur, 'value', cur)} -> {getattr(tgt, 'value', tgt)}"
        )


def ensure_step_transition(current: StepStatus | str, target: StepStatus | str) -> None:
    """@brief 校验 Step 状态转换，非法时抛出 InvalidStateTransition。"""
    if not can_transition_step(current, target):
        cur = _coerce_enum(StepStatus, current, current)
        tgt = _coerce_enum(StepStatus, target, target)
        raise InvalidStateTransition(
            f"非法 Step 状态转换: {getattr(cur, 'value', cur)} -> {getattr(tgt, 'value', tgt)}"
        )


class _JsonModel:
    """@brief 数据模型的 JSON 序列化基类，仅提供 to_dict/to_json/from_json。"""

    def to_dict(self) -> dict[str, Any]:
        return _serialize(asdict(self))

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_json(cls, text: str):
        return cls.from_dict(json.loads(text))


@dataclass
class VerificationResult(_JsonModel):
    """@brief 统一验证结论。Tool/Handler 返回 success 不等于本结论 PASS。"""

    status: VerificationStatus
    reason: str | None = None
    checks: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    manual_review_required: bool = False
    error_code: str | None = None
    schema_version: str = SCHEMA_VERSION

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "VerificationResult":
        return cls(
            status=_coerce_enum(VerificationStatus, data.get("status"), VerificationStatus.BLOCKED),
            reason=data.get("reason"),
            checks=list(data.get("checks") or []),
            artifacts=list(data.get("artifacts") or []),
            evidence=list(data.get("evidence") or []),
            manual_review_required=bool(data.get("manual_review_required", False)),
            error_code=data.get("error_code"),
            schema_version=str(data.get("schema_version", SCHEMA_VERSION)),
        )


@dataclass
class RecoveryDecision(_JsonModel):
    """@brief 结构化恢复决策（Recovery Engine 在后续 Phase 落地）。"""

    decision: str
    reason: str = ""
    retry_count: int = 0
    max_retries: int | None = None
    fallback_backend: str | None = None
    error_kind: str | None = None
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.decision not in RECOVERY_ACTIONS:
            raise ValueError(
                f"非法恢复决策 {self.decision!r}，允许值: {sorted(RECOVERY_ACTIONS)}"
            )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RecoveryDecision":
        return cls(
            decision=str(data.get("decision") or "block"),
            reason=str(data.get("reason") or ""),
            retry_count=int(data.get("retry_count") or 0),
            max_retries=data.get("max_retries"),
            fallback_backend=data.get("fallback_backend"),
            error_kind=data.get("error_kind"),
            schema_version=str(data.get("schema_version", SCHEMA_VERSION)),
        )


@dataclass
class ExecutionResult(_JsonModel):
    """@brief 单步执行结果。

    ``success`` 仅表示 Tool/Handler 层成功，**不等于任务最终成功**；需要 Review 的
    能力必须再经过 ``VerificationResult`` 判定后才能进入 COMPLETED。
    """

    success: bool = False
    message: str = ""
    outputs: list[Any] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    error_code: str | None = None
    error_kind: str | None = None
    retryable: bool = False
    schema_version: str = SCHEMA_VERSION

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ExecutionResult":
        return cls(
            success=bool(data.get("success", False)),
            message=str(data.get("message") or ""),
            outputs=list(data.get("outputs") or []),
            artifacts=list(data.get("artifacts") or []),
            evidence=list(data.get("evidence") or []),
            error_code=data.get("error_code"),
            error_kind=data.get("error_kind"),
            retryable=bool(data.get("retryable", False)),
            schema_version=str(data.get("schema_version", SCHEMA_VERSION)),
        )


@dataclass
class StepRecord(_JsonModel):
    """@brief 单个执行 Step 的记录，可被 Worker / MCP / CLI 复用。"""

    step_id: str
    tool_name: str = ""
    capability_id: str | None = None
    backend: str | None = None
    parent_step_id: str | None = None
    status: StepStatus = StepStatus.PENDING
    started_at: str | None = None
    finished_at: str | None = None
    duration_ms: int | None = None
    arguments_summary: dict[str, Any] = field(default_factory=dict)
    result_summary: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    retryable: bool = False
    retry_count: int = 0
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    verification: VerificationResult | None = None
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.step_id:
            raise ValueError("StepRecord.step_id 不能为空")

    def transition(self, target: StepStatus | str) -> "StepRecord":
        """@brief 校验并更新 Step 状态，非法转换抛 InvalidStateTransition。"""
        ensure_step_transition(self.status, target)
        self.status = _coerce_enum(StepStatus, target, self.status)
        return self

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "StepRecord":
        verification = data.get("verification")
        return cls(
            step_id=str(data.get("step_id") or ""),
            tool_name=str(data.get("tool_name") or ""),
            capability_id=data.get("capability_id"),
            backend=data.get("backend"),
            parent_step_id=data.get("parent_step_id"),
            status=_coerce_enum(StepStatus, data.get("status"), StepStatus.PENDING),
            started_at=data.get("started_at"),
            finished_at=data.get("finished_at"),
            duration_ms=data.get("duration_ms"),
            arguments_summary=dict(data.get("arguments_summary") or {}),
            result_summary=dict(data.get("result_summary") or {}),
            error_code=data.get("error_code"),
            retryable=bool(data.get("retryable", False)),
            retry_count=int(data.get("retry_count") or 0),
            artifacts=list(data.get("artifacts") or []),
            evidence=list(data.get("evidence") or []),
            verification=VerificationResult.from_dict(verification) if isinstance(verification, Mapping) else None,
            schema_version=str(data.get("schema_version", SCHEMA_VERSION)),
        )


@dataclass
class RunContext(_JsonModel):
    """@brief 一次 Run 的统一上下文，与 CAD Studio Queue Job 解耦。"""

    run_id: str
    goal: str = ""
    trace_id: str | None = None
    status: RunStatus = RunStatus.CREATED
    started_at: str | None = None
    finished_at: str | None = None
    current_step: str | None = None
    steps: list[StepRecord] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    retry_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.run_id:
            raise ValueError("RunContext.run_id 不能为空")
        if not self.trace_id:
            self.trace_id = self.run_id

    def transition(self, target: RunStatus | str) -> "RunContext":
        """@brief 校验并更新 Run 状态，非法转换抛 InvalidStateTransition。"""
        ensure_run_transition(self.status, target)
        self.status = _coerce_enum(RunStatus, target, self.status)
        return self

    def step(self, step_id: str) -> StepRecord | None:
        """@brief 按 step_id 查找已记录 Step。"""
        for item in self.steps:
            if item.step_id == step_id:
                return item
        return None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RunContext":
        raw_steps = data.get("steps") or []
        steps = [
            StepRecord.from_dict(item) if isinstance(item, Mapping) else StepRecord(step_id="")
            for item in raw_steps
        ]
        return cls(
            run_id=str(data.get("run_id") or ""),
            goal=str(data.get("goal") or ""),
            trace_id=data.get("trace_id") or data.get("run_id"),
            status=_coerce_enum(RunStatus, data.get("status"), RunStatus.CREATED),
            started_at=data.get("started_at"),
            finished_at=data.get("finished_at"),
            current_step=data.get("current_step"),
            steps=steps,
            artifacts=list(data.get("artifacts") or []),
            evidence=list(data.get("evidence") or []),
            errors=list(data.get("errors") or []),
            retry_count=int(data.get("retry_count") or 0),
            metadata=dict(data.get("metadata") or {}),
            schema_version=str(data.get("schema_version", SCHEMA_VERSION)),
        )


__all__ = [
    "InvalidStateTransition",
    "RECOVERY_ACTIONS",
    "RunContext",
    "RunStatus",
    "SCHEMA_VERSION",
    "StepRecord",
    "StepStatus",
    "ExecutionResult",
    "RecoveryDecision",
    "VerificationResult",
    "VerificationStatus",
    "can_transition_run",
    "can_transition_step",
    "ensure_run_transition",
    "ensure_step_transition",
    "now_iso",
]
