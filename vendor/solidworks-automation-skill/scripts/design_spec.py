"""
设计规格（design spec）解析与校验。

面向机械工程师的核心工作流：用一份**可版本控制的设计规格文件**描述零件，
再由执行器幂等地重建模型。相比让 AI 每次重新生成一套祈使式建模调用，规格
文件带来三个关键能力：

1. **可 diff / 可 commit**：工程师提交的是设计意图，而不是一次性的脚本。
2. **幂等可重建**：同一份规格任何时候构建出的特征树结构一致。
3. **内建验证**：``verify`` 段让构建后自动回读几何并与期望比对。

规格格式（单位默认 mm）：

.. code-block:: json

    {
      "schema_version": "1.0",
      "part_name": "motor_mount",
      "units": "mm",
      "base": {"type": "rect_plate", "width": 120, "height": 80, "thickness": 8},
      "holes": [
        {"id": "H1", "type": "through", "diameter": 6.6, "position": [15, 15]},
        {"id": "H2", "type": "blind", "diameter": 5.0, "depth": 6, "position": [15, 65]}
      ],
      "fillets": [{"radius": 4, "axis": "z", "convex_only": true}],
      "verify": {"envelope_mm": [120, 80, 8], "hole_count": 2,
                 "tolerance_mm": 0.1}
    }
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = "1.0"

SUPPORTED_UNITS = {"mm", "cm", "m", "in"}

# 单位换算到毫米
_UNIT_TO_MM = {
    "mm": 1.0,
    "cm": 10.0,
    "m": 1000.0,
    "in": 25.4,
}

BASE_TYPES = {"rect_plate", "cylinder", "none"}

HOLE_TYPES = {"through", "blind", "counterbore", "countersink"}

MAX_HOLES = 200
MAX_FILLETS = 50


class DesignSpecError(ValueError):
    """设计规格校验失败。"""

    def __init__(self, code, message, field=None):
        self.code = code
        self.field = field
        super().__init__(f"[{code}] {message}" + (f"（字段: {field}）" if field else ""))


def unit_scale(units: str) -> float:
    """返回该单位制到毫米的换算系数。"""
    key = str(units or "mm").strip().lower()
    if key not in _UNIT_TO_MM:
        raise DesignSpecError(
            "SPEC_UNIT_UNSUPPORTED",
            f"不支持的单位 {units!r}；可选 {sorted(_UNIT_TO_MM)}",
            "units",
        )
    return _UNIT_TO_MM[key]


def to_mm(value, units: str) -> float:
    """把规格中的长度值换算为毫米。"""
    try:
        return float(value) * unit_scale(units)
    except (TypeError, ValueError) as exc:
        raise DesignSpecError("SPEC_NUMBER_INVALID", f"期望数值，收到 {value!r}") from exc


def _positive(value, field, where=""):
    """校验正数。"""
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise DesignSpecError("SPEC_NUMBER_INVALID", f"期望数值，收到 {value!r}", field) from exc
    if number <= 0:
        raise DesignSpecError("SPEC_NOT_POSITIVE", f"必须为正数，收到 {number}", field)
    return number


def _position(value, field):
    """校验二维/三维坐标。"""
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        raise DesignSpecError("SPEC_POSITION_INVALID", f"期望 [x, y] 或 [x, y, z]，收到 {value!r}", field)
    result = []
    for item in value[:3]:
        try:
            result.append(float(item))
        except (TypeError, ValueError) as exc:
            raise DesignSpecError("SPEC_POSITION_INVALID", f"坐标含非数值 {item!r}", field) from exc
    while len(result) < 3:
        result.append(0.0)
    return result


def validate_design_spec(spec: Dict[str, Any]) -> Dict[str, Any]:
    """
    校验设计规格并归一化为毫米制。

    参数:
        spec: 解析后的规格字典（单位由 spec["units"] 决定，默认 mm）。

    返回:
        dict：status="ok" 时附带归一化后的 "normalized" 规格；否则 "errors"
        列出全部问题（一次性返回所有错误，而不是遇到第一个就停，方便用户一次改完）。
    """
    errors: List[Dict[str, Any]] = []
    warnings: List[str] = []

    if not isinstance(spec, dict):
        return {
            "status": "error",
            "errors": [{"code": "SPEC_NOT_OBJECT", "message": "规格必须是 JSON 对象"}],
            "warnings": [],
        }

    version = str(spec.get("schema_version", SCHEMA_VERSION))
    if version != SCHEMA_VERSION:
        warnings.append(
            f"规格 schema_version={version}，当前执行器版本为 {SCHEMA_VERSION}；"
            "将按当前版本解析，字段差异可能被忽略。"
        )

    part_name = spec.get("part_name")
    if part_name is not None and not str(part_name).strip():
        errors.append({"code": "SPEC_PART_NAME_EMPTY", "message": "part_name 不能为空字符串", "field": "part_name"})

    units = str(spec.get("units", "mm"))
    try:
        scale = unit_scale(units)
    except DesignSpecError as exc:
        return {"status": "error", "errors": [{"code": exc.code, "message": str(exc), "field": exc.field}], "warnings": warnings}

    normalized: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "part_name": str(part_name or "part").strip() or "part",
        "source_units": units,
        "holes": [],
        "fillets": [],
    }

    # ---- base ----
    base_declared = "base" in spec and spec.get("base") is not None
    base = spec.get("base") or {}
    if not isinstance(base, dict):
        errors.append({"code": "SPEC_BASE_INVALID", "message": "base 必须是对象", "field": "base"})
        base = {}
        base_declared = False
    # 缺省 base 与显式 base.type="none" 含义不同：前者多半是用户漏写，
    # 会建出一个空文档；后者是"只要后续特征"的明确意图。
    base_type = str(base.get("type", "none")).strip().lower()
    if not base_declared and base_type == "none":
        errors.append({
            "code": "SPEC_EMPTY",
            "message": (
                "规格未定义基础实体。请提供 base（rect_plate 或 cylinder）；"
                "若确实只需后续特征，请显式写 base.type=\"none\"。"
            ),
            "field": "base",
        })
    if base_type not in BASE_TYPES:
        errors.append({
            "code": "SPEC_BASE_TYPE",
            "message": f"不支持的 base.type={base_type!r}；可选 {sorted(BASE_TYPES)}",
            "field": "base.type",
        })
    else:
        entry: Dict[str, Any] = {"type": base_type}
        if base_type == "rect_plate":
            for key, mm_key in (("width", "width_mm"), ("height", "height_mm"), ("thickness", "thickness_mm")):
                if key not in base:
                    errors.append({"code": "SPEC_FIELD_MISSING", "message": f"rect_plate 缺少 {key}", "field": f"base.{key}"})
                    continue
                try:
                    entry[mm_key] = round(_positive(base[key], f"base.{key}") * scale, 6)
                except DesignSpecError as exc:
                    errors.append({"code": exc.code, "message": str(exc), "field": exc.field})
        elif base_type == "cylinder":
            for key, mm_key in (("diameter", "diameter_mm"), ("height", "height_mm")):
                if key not in base:
                    errors.append({"code": "SPEC_FIELD_MISSING", "message": f"cylinder 缺少 {key}", "field": f"base.{key}"})
                    continue
                try:
                    entry[mm_key] = round(_positive(base[key], f"base.{key}") * scale, 6)
                except DesignSpecError as exc:
                    errors.append({"code": exc.code, "message": str(exc), "field": exc.field})
        normalized["base"] = entry

    # ---- holes ----
    holes = spec.get("holes") or []
    if not isinstance(holes, list):
        errors.append({"code": "SPEC_HOLES_INVALID", "message": "holes 必须是数组", "field": "holes"})
        holes = []
    elif len(holes) > MAX_HOLES:
        errors.append({
            "code": "SPEC_HOLES_TOO_MANY",
            "message": f"holes 数量 {len(holes)} 超过上限 {MAX_HOLES}",
            "field": "holes",
        })
        holes = holes[:MAX_HOLES]

    seen_ids = set()
    for index, hole in enumerate(holes):
        where = f"holes[{index}]"
        if not isinstance(hole, dict):
            errors.append({"code": "SPEC_HOLE_INVALID", "message": "孔必须是对象", "field": where})
            continue
        hole_type = str(hole.get("type", "through")).strip().lower()
        if hole_type not in HOLE_TYPES:
            errors.append({
                "code": "SPEC_HOLE_TYPE",
                "message": f"不支持的孔类型 {hole_type!r}；可选 {sorted(HOLE_TYPES)}",
                "field": f"{where}.type",
            })
            continue

        entry = {"type": hole_type}
        hole_id = hole.get("id")
        if hole_id is not None:
            hole_id = str(hole_id)
            if hole_id in seen_ids:
                errors.append({"code": "SPEC_HOLE_ID_DUPLICATE", "message": f"孔 id 重复: {hole_id}", "field": f"{where}.id"})
            seen_ids.add(hole_id)
            entry["id"] = hole_id
        else:
            warnings.append(f"{where} 未提供 id；建议为每个孔命名以便追溯检验记录。")
            entry["id"] = f"H{index + 1}"

        try:
            entry["diameter_mm"] = round(_positive(hole.get("diameter"), f"{where}.diameter") * scale, 6)
        except DesignSpecError as exc:
            errors.append({"code": exc.code, "message": str(exc), "field": exc.field})
        try:
            entry["position_mm"] = [round(value * scale, 6) for value in _position(hole.get("position"), f"{where}.position")]
        except DesignSpecError as exc:
            errors.append({"code": exc.code, "message": str(exc), "field": exc.field})

        if hole_type == "blind":
            if hole.get("depth") is None:
                errors.append({"code": "SPEC_FIELD_MISSING", "message": "盲孔必须给出 depth", "field": f"{where}.depth"})
            else:
                try:
                    entry["depth_mm"] = round(_positive(hole["depth"], f"{where}.depth") * scale, 6)
                except DesignSpecError as exc:
                    errors.append({"code": exc.code, "message": str(exc), "field": exc.field})
        elif hole_type == "counterbore":
            for key, mm_key in (("counterbore_diameter", "counterbore_diameter_mm"), ("counterbore_depth", "counterbore_depth_mm")):
                if hole.get(key) is None:
                    errors.append({"code": "SPEC_FIELD_MISSING", "message": f"沉头孔必须给出 {key}", "field": f"{where}.{key}"})
                    continue
                try:
                    entry[mm_key] = round(_positive(hole[key], f"{where}.{key}") * scale, 6)
                except DesignSpecError as exc:
                    errors.append({"code": exc.code, "message": str(exc), "field": exc.field})
        elif hole_type == "countersink":
            for key, mm_key in (("countersink_diameter", "countersink_diameter_mm"), ("angle", "angle_deg")):
                if hole.get(key) is None:
                    errors.append({"code": "SPEC_FIELD_MISSING", "message": f"锥沉孔必须给出 {key}", "field": f"{where}.{key}"})
                    continue
                if key == "angle":
                    entry[mm_key] = float(hole[key])
                else:
                    try:
                        entry[mm_key] = round(_positive(hole[key], f"{where}.{key}") * scale, 6)
                    except DesignSpecError as exc:
                        errors.append({"code": exc.code, "message": str(exc), "field": exc.field})

        normalized["holes"].append(entry)

    # ---- fillets ----
    fillets = spec.get("fillets") or []
    if not isinstance(fillets, list):
        errors.append({"code": "SPEC_FILLETS_INVALID", "message": "fillets 必须是数组", "field": "fillets"})
        fillets = []
    elif len(fillets) > MAX_FILLETS:
        errors.append({
            "code": "SPEC_FILLETS_TOO_MANY",
            "message": f"fillets 数量 {len(fillets)} 超过上限 {MAX_FILLETS}",
            "field": "fillets",
        })
        fillets = fillets[:MAX_FILLETS]

    for index, fillet in enumerate(fillets):
        where = f"fillets[{index}]"
        if not isinstance(fillet, dict):
            errors.append({"code": "SPEC_FILLET_INVALID", "message": "圆角必须是对象", "field": where})
            continue
        entry = {}
        try:
            entry["radius_mm"] = round(_positive(fillet.get("radius"), f"{where}.radius") * scale, 6)
        except DesignSpecError as exc:
            errors.append({"code": exc.code, "message": str(exc), "field": exc.field})
        axis = str(fillet.get("axis", "z")).strip().lower()
        if axis not in {"x", "y", "z", "vertical", "all"}:
            errors.append({"code": "SPEC_FILLET_AXIS", "message": f"不支持的 axis={axis!r}", "field": f"{where}.axis"})
        else:
            entry["axis"] = axis
        for flag in ("convex_only", "concave_only"):
            if flag in fillet:
                entry[flag] = bool(fillet[flag])
        if entry.get("convex_only") and entry.get("concave_only"):
            errors.append({"code": "SPEC_FILLET_FLAGS", "message": "convex_only 与 concave_only 不能同时为真", "field": where})
        normalized["fillets"].append(entry)

    # ---- fillet 半径可行性 ----
    thickness = (normalized.get("base") or {}).get("thickness_mm")
    for index, fillet in enumerate(normalized["fillets"]):
        radius = fillet.get("radius_mm")
        if radius is None or not thickness:
            continue
        if radius * 2 > thickness:
            warnings.append(
                f"fillets[{index}] 半径 {radius}mm 超过板厚 {thickness}mm 的一半，"
                "SolidWorks 可能无法生成或产生自交，请确认设计意图。"
            )

    # ---- verify ----
    verify = spec.get("verify") or {}
    if verify and not isinstance(verify, dict):
        errors.append({"code": "SPEC_VERIFY_INVALID", "message": "verify 必须是对象", "field": "verify"})
        verify = {}
    if verify:
        normalized_verify: Dict[str, Any] = {}
        if verify.get("envelope_mm") is not None:
            try:
                normalized_verify["envelope_mm"] = [round(value * scale, 6) for value in _position(verify["envelope_mm"], "verify.envelope_mm")]
            except DesignSpecError as exc:
                errors.append({"code": exc.code, "message": str(exc), "field": exc.field})
        if verify.get("hole_count") is not None:
            try:
                normalized_verify["hole_count"] = int(verify["hole_count"])
            except (TypeError, ValueError) as exc:
                errors.append({"code": "SPEC_NUMBER_INVALID", "message": "verify.hole_count 必须是整数", "field": "verify.hole_count"})
        if verify.get("tolerance_mm") is not None:
            try:
                normalized_verify["tolerance_mm"] = abs(float(verify["tolerance_mm"]))
            except (TypeError, ValueError) as exc:
                errors.append({"code": "SPEC_NUMBER_INVALID", "message": "verify.tolerance_mm 必须是数值", "field": "verify.tolerance_mm"})
        if verify.get("min_mass_g") is not None:
            try:
                normalized_verify["min_mass_g"] = float(verify["min_mass_g"])
            except (TypeError, ValueError) as exc:
                errors.append({"code": "SPEC_NUMBER_INVALID", "message": "verify.min_mass_g 必须是数值", "field": "verify.min_mass_g"})
        if verify.get("max_mass_g") is not None:
            try:
                normalized_verify["max_mass_g"] = float(verify["max_mass_g"])
            except (TypeError, ValueError) as exc:
                errors.append({"code": "SPEC_NUMBER_INVALID", "message": "verify.max_mass_g 必须是数值", "field": "verify.max_mass_g"})
        normalized["verify"] = normalized_verify
    else:
        normalized["verify"] = {}

    return {
        "status": "ok" if not errors else "error",
        "errors": errors,
        "warnings": warnings,
        "normalized": normalized if not errors else None,
    }


def load_design_spec(path) -> Dict[str, Any]:
    """
    读取并校验设计规格文件（.json）。

    参数:
        path: 规格文件路径。

    返回:
        validate_design_spec 的结果，额外附带 "source_path"。
    """
    resolved = Path(str(path)).expanduser().resolve()
    if not resolved.is_file():
        return {
            "status": "error",
            "errors": [{"code": "SPEC_FILE_MISSING", "message": f"规格文件不存在: {resolved}"}],
            "warnings": [],
            "source_path": str(resolved),
        }
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {
            "status": "error",
            "errors": [{"code": "SPEC_JSON_INVALID", "message": f"JSON 解析失败: {exc}"}],
            "warnings": [],
            "source_path": str(resolved),
        }
    result = validate_design_spec(payload)
    result["source_path"] = str(resolved)
    return result


def compare_verification(actual: Dict[str, Any], expected: Dict[str, Any]) -> Dict[str, Any]:
    """
    把构建后的实测几何与规格的 verify 段比对。

    参数:
        actual: 构建后回读的结果，含 envelope_mm / hole_count / mass_g。
        expected: 规格中归一化后的 verify 段。

    返回:
        dict：status 为 "pass" | "warn" | "skipped"；checks 列出每项比对结论。

    说明:
        比对失败返回 "warn" 而不是 "error"：几何不匹配可能来自设计变更而非执行
        缺陷，必须交给工程师判断。绝不静默通过。
    """
    checks: List[Dict[str, Any]] = []
    tolerance = float(expected.get("tolerance_mm", 0.1) or 0.1)

    expected_envelope = expected.get("envelope_mm")
    actual_size = actual.get("envelope_mm") or actual.get("size_mm")
    if expected_envelope and actual_size:
        deltas = []
        for axis in range(3):
            want = float(expected_envelope[axis]) if axis < len(expected_envelope) else 0.0
            got = float(actual_size[axis]) if axis < len(actual_size) else 0.0
            deltas.append(abs(got - want))
        passed = max(deltas) <= tolerance
        checks.append({
            "name": "envelope_mm",
            "expected": list(expected_envelope),
            "actual": list(actual_size),
            "max_delta_mm": round(max(deltas), 6),
            "tolerance_mm": tolerance,
            "passed": passed,
        })
    elif expected_envelope:
        checks.append({
            "name": "envelope_mm",
            "expected": list(expected_envelope),
            "actual": None,
            "passed": False,
            "note": "未能回读包围盒，无法验证尺寸。",
        })

    if expected.get("hole_count") is not None:
        actual_count = actual.get("hole_count")
        checks.append({
            "name": "hole_count",
            "expected": expected["hole_count"],
            "actual": actual_count,
            "passed": actual_count == expected["hole_count"],
        })

    mass_g = actual.get("mass_g")
    if expected.get("min_mass_g") is not None:
        checks.append({
            "name": "min_mass_g",
            "expected": expected["min_mass_g"],
            "actual": mass_g,
            "passed": mass_g is not None and mass_g >= expected["min_mass_g"],
        })
    if expected.get("max_mass_g") is not None:
        checks.append({
            "name": "max_mass_g",
            "expected": expected["max_mass_g"],
            "actual": mass_g,
            "passed": mass_g is not None and mass_g <= expected["max_mass_g"],
        })

    if not checks:
        return {"status": "skipped", "checks": [], "note": "规格未提供 verify 段，跳过几何验证。"}

    failed = [check for check in checks if not check["passed"]]
    return {
        "status": "pass" if not failed else "warn",
        "checks": checks,
        "failed": [check["name"] for check in failed],
        "manual_review_required": bool(failed),
    }
