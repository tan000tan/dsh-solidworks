"""@brief Execution Core 内部能力包（内部实现，不是用户入口）。

本包只承载「可靠执行」的轻量数据模型与适配层：
- ``state``        统一执行状态模型
- ``capability``   capabilities.yaml 的 Facade（复用现有 router）
- ``trace``        复用 queue/events 的 append-only Execution Trace adapter
- ``verification`` 把既有 Reviewer 结果统一成 VerificationResult 的 Adapter
- ``recovery``     失败后的纯确定性决策层（分类 + 决策，不执行动作）
- ``execution``    内部编排层（State + Handler + Verification + Recovery + Trace）

注意：``scripts/__init__.py`` 会在导入时触发 ``sw_connect`` 的 COM 依赖加载，
因此无 SolidWorks 的 CI 应通过顶层 ``core.*``（``scripts/`` 加入 sys.path）导入
本包，避免触发 pywin32 交互。
"""
from .capability import (
    capability_gap,
    get_backend_candidates,
    get_capability,
    get_capability_status,
    get_operation_route,
    load_capabilities,
    requires_review,
    resolve_backend,
)
from .state import (
    InvalidStateTransition,
    RECOVERY_ACTIONS,
    SCHEMA_VERSION,
    ExecutionResult,
    RecoveryDecision,
    RunContext,
    RunStatus,
    StepRecord,
    StepStatus,
    VerificationResult,
    VerificationStatus,
    can_transition_run,
    can_transition_step,
    ensure_run_transition,
    ensure_step_transition,
    now_iso,
)
from .trace import (
    TRACE_EVENT_TYPES,
    append_event,
    emit,
    events_dir,
    read_events,
    redact,
    sanitize_id,
    trace_path_for,
)
from .verification import (
    aggregate_checks,
    aggregate_statuses,
    check_status,
    normalize_status,
    verify,
)
from .recovery import (
    DEFAULT_MAX_RETRIES,
    ErrorKind,
    classify_error,
    decide,
)
from .execution import (
    ExecutionAssessment,
    execute_with_core,
)

__all__ = [
    # state
    "InvalidStateTransition",
    "RECOVERY_ACTIONS",
    "SCHEMA_VERSION",
    "ExecutionResult",
    "RecoveryDecision",
    "RunContext",
    "RunStatus",
    "StepRecord",
    "StepStatus",
    "VerificationResult",
    "VerificationStatus",
    "can_transition_run",
    "can_transition_step",
    "ensure_run_transition",
    "ensure_step_transition",
    "now_iso",
    # capability
    "capability_gap",
    "get_backend_candidates",
    "get_capability",
    "get_capability_status",
    "get_operation_route",
    "load_capabilities",
    "requires_review",
    "resolve_backend",
    # trace
    "TRACE_EVENT_TYPES",
    "append_event",
    "emit",
    "events_dir",
    "read_events",
    "redact",
    "sanitize_id",
    "trace_path_for",
    # verification
    "aggregate_checks",
    "aggregate_statuses",
    "check_status",
    "normalize_status",
    "verify",
    # recovery
    "DEFAULT_MAX_RETRIES",
    "ErrorKind",
    "classify_error",
    "decide",
    # execution
    "ExecutionAssessment",
    "execute_with_core",
]
