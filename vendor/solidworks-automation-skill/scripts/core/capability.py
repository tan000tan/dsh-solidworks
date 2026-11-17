"""@brief Capability Facade —— capabilities.yaml 唯一真源的适配层。

本模块**不是**新的 Registry。它只把 ``scripts/capabilities.py`` 里已经存在的
能力索引、后端解析、操作路由等能力收敛成一组稳定接口，供 Execution Core /
Worker / MCP 复用。

约束：
- 不新增 ``tool_registry.yaml`` / ``runtime_capabilities.yaml`` / ``agent_capabilities.json``；
- 不做 Tool 检索（Tool Missing != Capability Missing），也不做 Planning；
- 找不到能力时只返回结构化的 ``capability_gap``，把控制权交还上层 Agent。
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

try:
    from .. import capabilities as _capabilities
except ImportError:  # 以顶层 core 包导入时复用 scripts/capabilities.py
    import capabilities as _capabilities


def load_capabilities(path: str | None = None) -> dict[str, Any]:
    """@brief 读取并校验能力真源（复用 scripts/capabilities.py）。"""
    return _capabilities.load_capabilities(path)


def get_capability(capability_id: str, payload: Mapping[str, Any] | None = None) -> dict[str, Any] | None:
    """@brief 按 ID 返回能力条目，未知能力返回 None。"""
    item = _capabilities.capability_index(payload).get(str(capability_id))
    return dict(item) if item else None


def get_operation_route(operation_id: str, payload: Mapping[str, Any] | None = None) -> dict[str, Any] | None:
    """@brief 按 ID 返回原子操作后端路由，未知路由返回 None。"""
    item = _capabilities.operation_route_index(payload).get(str(operation_id))
    return dict(item) if item else None


def get_backend_candidates(operation_id: str, payload: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    """@brief 返回某原子操作的候选后端（按 priority 升序）。"""
    route = get_operation_route(operation_id, payload)
    if route is None:
        return []
    candidates = [item for item in (route.get("candidates") or []) if isinstance(item, dict)]
    return sorted(candidates, key=lambda item: int(item.get("priority") or 0))


def resolve_backend(
    operation_id: str,
    *,
    available_backends: Iterable[str] | None = None,
    available_requirements: Iterable[str] | None = None,
    solidworks_revision: str | None = None,
    exact_api: bool = False,
    payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """@brief 按语义/版本/依赖/可用运行时选择后端（直接复用现有 router）。"""
    return _capabilities.resolve_operation_backend(
        str(operation_id),
        available_backends=available_backends,
        available_requirements=available_requirements,
        solidworks_revision=solidworks_revision,
        exact_api=exact_api,
        payload=payload,
    )


def requires_review(
    *,
    capability_id: str | None = None,
    operation_id: str | None = None,
    payload: Mapping[str, Any] | None = None,
) -> bool | None:
    """@brief 判断能力/操作是否需要 Review；未知时返回 None。

    - 提供 operation_id 时，以 operation_routes 的 review_required 为准；
    - 提供 capability_id 时，非 verified 等级一律需要 Review。
    """
    if operation_id is not None:
        route = get_operation_route(operation_id, payload)
        return None if route is None else bool(route.get("review_required", True))
    if capability_id is not None:
        item = get_capability(capability_id, payload)
        return None if item is None else item.get("level") != "verified"
    return None


def get_capability_status(capability_id: str, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """@brief 返回能力结构化状态，未知能力用 ``status: unknown`` 表达。"""
    item = get_capability(capability_id, payload)
    if item is None:
        return {
            "status": "unknown",
            "capability_id": str(capability_id),
            "level": None,
            "review_required": None,
            "unattended_allowed": False,
            "verified_versions": [],
            "allowed_modes": [],
            "backends": [],
            "capability": None,
            "reason": "能力不在 capabilities.yaml 真源中",
        }
    level = item.get("level", "not_implemented")
    return {
        "status": level,
        "capability_id": str(capability_id),
        "level": level,
        "review_required": level != "verified",
        "unattended_allowed": _capabilities.unattended_allowed([str(capability_id)], payload),
        "verified_versions": list(item.get("verified_versions") or []),
        "allowed_modes": list(item.get("allowed_modes") or []),
        "backends": list(item.get("backends") or []),
        "capability": item,
    }


def capability_gap(
    requested_capability: str,
    reason: str = "",
    *,
    searched_existing_tools: bool = True,
    searched_backends: bool = True,
) -> dict[str, Any]:
    """@brief 返回结构化 CAPABILITY_GAP，把控制权交还上层 Agent。

    第一版 V2 不联网、不自动解决缺口；由上层 Codex/Claude 依据 SKILL.md 的
    ``未封装 API 规则`` 自行查证、实现、真机运行与沉淀。
    """
    return {
        "status": "capability_gap",
        "requested_capability": str(requested_capability),
        "reason": str(reason),
        "searched_existing_tools": bool(searched_existing_tools),
        "searched_backends": bool(searched_backends),
        "recommended_action": "agent_resolution_required",
    }


__all__ = [
    "capability_gap",
    "get_backend_candidates",
    "get_capability",
    "get_capability_status",
    "get_operation_route",
    "load_capabilities",
    "requires_review",
    "resolve_backend",
]
