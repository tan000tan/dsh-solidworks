"""
sw_compat.py - SolidWorks 2020-2026 多版本环境兼容与降级调度核心

本模块为 DSH-SolidWorks 提供工业级多版本兼容保障：
1. 真实版本与实例识别：
   - 精准解析 COM RevisionNumber，提取年份、Service Pack 与 Hotfix。
   - 绑定实际连接的 SolidWorks PID，支持多实例精准映射。
   - 杜绝未知版本静默假定为 2026 的缺陷。
2. 严格的异常分类机制：
   - 严格区分“COM 接口/参数缺失”与“CAD 几何业务失败”。
   - 仅在确认属于 DISP_E_MEMBERNOTFOUND / DISP_E_BADPARAMCOUNT / AttributeError 时执行 API 降级。
   - 几何错误（草图未封闭、自相交等）保留原始异常，杜绝盲目重试产生脏特征。
3. 核心 CAD API 语义对齐与平滑回退：
   - 拉伸凸台：FeatureExtrusion3 (23参数) -> FeatureExtrusion2 (19参数)
   - 拉伸切除：FeatureCut4 (27参数) -> FeatureCut3 (21参数)，双向方向自愈
   - 镜像特征：InsertMirrorFeature2 -> InsertMirrorFeature
   - 质量属性：CreateMassProperty (高精度对象) -> GetMassProperties2 (数组)
   - 装配配合：AddMate5 -> AddMate3 / CreateMate
   - 工程图视图：CreateDrawViewFromModelView3 -> CreateDrawViewFromModelView2
4. 审计追踪与中文友好诊断 (SolidWorksCompatError)。
"""

from __future__ import annotations

import logging
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("sw_compat")

# 明确定义的 COM 接口与分派错误码 (HRESULT)
COM_DISP_ERRORS = {
    -2147352573: "DISP_E_MEMBERNOTFOUND (0x80020003: 成员不存在)",
    -2147352562: "DISP_E_BADPARAMCOUNT (0x8002000E: 参数个数不匹配)",
    -2147352561: "DISP_E_PARAMNOTOPTIONAL (0x8002000F: 缺少必填参数)",
    -2147352565: "DISP_E_TYPEMISMATCH (0x80020005: 参数类型不匹配)",
    -2147352570: "DISP_E_UNKNOWNNAME (0x80020006: 未知名称)",
}


class SolidWorksCompatError(Exception):
    """多版本兼容性异常基类，带有结构化中文诊断与版本上下文。"""
    def __init__(
        self,
        message: str,
        version: Optional[int] = None,
        sp: Optional[int] = None,
        feature: Optional[str] = None,
        original_error: Optional[Exception] = None,
        degradation_attempted: bool = False
    ):
        super().__init__(message)
        self.message = message
        self.version = version
        self.sp = sp
        self.feature = feature
        self.original_error = original_error
        self.degradation_attempted = degradation_attempted

    def __str__(self) -> str:
        ver_str = f"SolidWorks {self.version}" if self.version else "当前 SolidWorks 环境"
        if self.sp is not None:
            ver_str += f" SP{self.sp}"
        prefix = f"[{ver_str}] " if ver_str else ""
        return f"{prefix}{self.message}"


@dataclass
class DegradationEvent:
    """记录一次 API 降级调度事件，供审计与追踪复核。"""
    timestamp: float
    feature: str
    target_version: Optional[int]
    primary_api: str
    fallback_api: str
    reason: str
    success: bool
    details: Dict[str, Any] = field(default_factory=dict)


# 全局降级事件日志（可供测试与审计导出）
GLOBAL_DEGRADATION_LOG: List[DegradationEvent] = []


def is_com_interface_mismatch_error(exc: Exception) -> bool:
    """
    严密判定异常是否为 COM 接口/方法缺失或签名不匹配。
    严格排除几何建模自相交、选择集为空、无草图等业务建模失败！
    """
    if isinstance(exc, AttributeError):
        return True
    
    # 针对 win32com 的 pywintypes.com_error 检查 HRESULT
    hresult = None
    args = getattr(exc, "args", None)
    if args and isinstance(args, (list, tuple)) and len(args) > 0:
        if isinstance(args[0], int):
            hresult = args[0]
        elif len(args) > 1 and isinstance(args[1], (list, tuple)) and len(args[1]) > 5:
            # 常见结构 (hresult, text, details, ...)
            try:
                hresult = int(args[0])
            except Exception:
                pass

    if hresult in COM_DISP_ERRORS:
        return True

    # 检查异常文本中的特征关键字
    err_str = str(exc).lower()
    mismatch_keywords = [
        "dispid", "not found", "找不到成员", "非选择性的参数",
        "disp_e_badparamcount", "disp_e_membernotfound", "disp_e_paramnotoptional",
        "has no attribute", "parameter mismatch"
    ]
    return any(k in err_str for k in mismatch_keywords)


def parse_solidworks_version_info(rev_str: Any) -> Dict[str, Any]:
    """
    从 RevisionNumber 字符串解析出结构化的版本字典：
    {
        "raw": "34.4.1",
        "major": 34,
        "year": 2026,
        "sp": 4,
        "hotfix": 1,
        "valid": True
    }
    若无法识别或格式异常，严禁猜测，显式返回 year=None 与 valid=False。
    """
    result = {
        "raw": str(rev_str) if rev_str is not None else "",
        "major": None,
        "year": None,
        "sp": None,
        "hotfix": None,
        "valid": False
    }

    if not rev_str or not isinstance(rev_str, str):
        return result

    parts = rev_str.strip().split(".")
    try:
        major = int(parts[0])
        result["major"] = major
        
        # SolidWorks 内部 Major 与年份官方映射：
        # 28 -> 2020, 29 -> 2021, 30 -> 2022, 31 -> 2023, 32 -> 2024, 33 -> 2025, 34 -> 2026
        if 28 <= major <= 40:
            result["year"] = 2020 + (major - 28)
            result["valid"] = True
        elif 2000 <= major <= 2035:
            result["year"] = major
            result["valid"] = True

        if len(parts) > 1:
            try:
                result["sp"] = int(parts[1])
            except ValueError:
                pass
        if len(parts) > 2:
            try:
                result["hotfix"] = int(parts[2])
            except ValueError:
                pass

    except (ValueError, IndexError):
        pass

    return result


def get_solidworks_version_info(sw: Any) -> Dict[str, Any]:
    """从已连接的 SolidWorks COM 实例获取版本结构化信息。"""
    rev = None
    try:
        from sw_connect import get_com_member
        rev = get_com_member(sw, "RevisionNumber")
    except Exception:
        try:
            m = getattr(sw, "RevisionNumber", None)
            rev = m() if callable(m) else m
        except Exception:
            pass
    info = parse_solidworks_version_info(rev)
    info["raw_revision"] = str(rev) if rev is not None else None
    return info


def detect_solidworks_capabilities(sw: Any, target_pid: Optional[int] = None) -> Dict[str, Any]:
    """
    对已连接的 SolidWorks COM 实例进行版本与接口能力动态探测。
    杜绝将未知实例假定为 2026 的缺陷；以反射与实际 COM 特性为准。
    """
    capabilities: Dict[str, Any] = {
        "raw_revision": "Unknown",
        "detected_year": None,  # 真实识别前为 None，严禁盲目默认 2026！
        "service_pack": None,
        "hotfix": None,
        "bound_pid": target_pid,
        "api_tier": "unknown",
        "supported_apis": {
            "FeatureExtrusion3": False,
            "FeatureExtrusion2": False,
            "FeatureCut4": False,
            "FeatureCut3": False,
            "InsertMirrorFeature2": False,
            "InsertMirrorFeature": False,
            "CreateMassProperty": False,
            "GetMassProperties2": False,
            "AddMate5": False,
            "CreateDrawViewFromModelView3": False
        },
        "degradation_routes": {}
    }

    if sw is None:
        return capabilities

    # 1. 精确获取 RevisionNumber
    try:
        from sw_connect import get_com_member
        rev = get_com_member(sw, "RevisionNumber")
    except Exception:
        try:
            m = getattr(sw, "RevisionNumber", None)
            rev = m() if callable(m) else m
        except Exception:
            rev = None

    if rev:
        capabilities["raw_revision"] = str(rev)
        vinfo = parse_solidworks_version_info(str(rev))
        if vinfo["valid"]:
            capabilities["detected_year"] = vinfo["year"]
            capabilities["service_pack"] = vinfo["sp"]
            capabilities["hotfix"] = vinfo["hotfix"]

    # 2. 获取实际绑定的进程 PID
    try:
        from sw_connect import get_com_member
        actual_pid = get_com_member(sw, "GetProcessID")
        if actual_pid:
            capabilities["bound_pid"] = int(actual_pid)
    except Exception:
        pass

    # 3. 动态探测 FeatureManager 与 Extension 接口 (优先从活动文档探测，或由已检测年份推导标准能力)
    year = capabilities["detected_year"]
    active_doc = None
    try:
        from sw_connect import get_com_member
        active_doc = get_com_member(sw, "ActiveDoc")
    except Exception:
        pass

    feat_mgr = None
    ext = None
    if active_doc:
        try:
            from sw_connect import get_com_member
            feat_mgr = get_com_member(active_doc, "FeatureManager")
            ext = get_com_member(active_doc, "Extension")
        except Exception:
            pass

    for api_name in [
        "FeatureExtrusion3", "FeatureExtrusion2",
        "FeatureCut4", "FeatureCut3",
        "InsertMirrorFeature2", "InsertMirrorFeature"
    ]:
        if feat_mgr:
            capabilities["supported_apis"][api_name] = hasattr(feat_mgr, api_name)
        elif year:
            if api_name in ("FeatureExtrusion3", "FeatureCut4", "InsertMirrorFeature2"):
                capabilities["supported_apis"][api_name] = (year >= 2024)
            else:
                capabilities["supported_apis"][api_name] = True

    for api_name in ["CreateMassProperty", "GetMassProperties2"]:
        if ext:
            capabilities["supported_apis"][api_name] = hasattr(ext, api_name)
        elif year:
            capabilities["supported_apis"][api_name] = True

    if active_doc and hasattr(active_doc, "AddMate5"):
        capabilities["supported_apis"]["AddMate5"] = True
    elif year:
        capabilities["supported_apis"]["AddMate5"] = (year >= 2024)

    if active_doc and hasattr(active_doc, "CreateDrawViewFromModelView3"):
        capabilities["supported_apis"]["CreateDrawViewFromModelView3"] = True
    elif year:
        capabilities["supported_apis"]["CreateDrawViewFromModelView3"] = (year >= 2024)

    # 5. 确定能力阶梯
    year = capabilities["detected_year"]
    if year is not None:
        if year >= 2024:
            capabilities["api_tier"] = "modern"
        elif year >= 2021:
            capabilities["api_tier"] = "stable"
        else:
            capabilities["api_tier"] = "legacy_compat"
    else:
        capabilities["api_tier"] = "dynamic_probed"

    # 6. 配置降级路径
    capabilities["degradation_routes"] = {
        "extrusion": "FeatureExtrusion3" if capabilities["supported_apis"].get("FeatureExtrusion3", False) else "FeatureExtrusion2",
        "cut": "FeatureCut4" if capabilities["supported_apis"].get("FeatureCut4", False) else "FeatureCut3",
        "mirror": "InsertMirrorFeature2" if capabilities["supported_apis"].get("InsertMirrorFeature2", False) else "InsertMirrorFeature",
        "mass": "CreateMassProperty" if capabilities["supported_apis"].get("CreateMassProperty", False) else "GetMassProperties2"
    }

    return capabilities


# ============================================================================
# API 自适应调度器与参数自适应转换实现
# ============================================================================

def safe_extrude_boss(
    feat_mgr: Any,
    single_dir: bool = True,
    flip: bool = False,
    direction: bool = True,
    termination1: int = 0,
    termination2: int = 0,
    depth1: float = 0.01,
    depth2: float = 0.0,
    draft_both: bool = False,
    draft1: bool = False,
    draft2: bool = False,
    draft_angle1: float = 0.0,
    draft_angle2: float = 0.0,
    draft_outward1: bool = False,
    draft_outward2: bool = False,
    merge: bool = True,
    use_feature_scope: bool = False,
    auto_select: bool = True,
    start_condition: int = 0,
    start_offset: float = 0.0,
    flip_start_offset: bool = False,
    current_year: Optional[int] = None
) -> Any:
    """
    多版本拉伸凸台/基体调度：
    1. 首选 FeatureExtrusion3 (23 参数)。
    2. 若触发接口/参数不匹配异常 (DISP_E_MEMBERNOTFOUND 等)，安全回退至 FeatureExtrusion2 (19 参数)。
    3. 严禁把几何建模失败当成接口不兼容；几何错误直接向上抛出。
    """
    extrude3 = getattr(feat_mgr, "FeatureExtrusion3", None)
    if callable(extrude3):
        try:
            feat = extrude3(
                single_dir, flip, direction, termination1, termination2,
                depth1, depth2, draft_both, draft1, draft2,
                draft_angle1, draft_angle2, draft_outward1, draft_outward2,
                False, False, False, merge, use_feature_scope, auto_select,
                start_condition, start_offset, flip_start_offset
            )
            if feat:
                return feat
        except Exception as e:
            if not is_com_interface_mismatch_error(e):
                # 几何错误或参数语义错误：严禁盲目重试，保留现场！
                raise
            logger.info(f"FeatureExtrusion3 接口缺失/签名不匹配 ({e})，正在平滑回退 FeatureExtrusion2...")
            GLOBAL_DEGRADATION_LOG.append(DegradationEvent(
                timestamp=time.time(),
                feature="extrude_boss",
                target_version=current_year,
                primary_api="FeatureExtrusion3",
                fallback_api="FeatureExtrusion2",
                reason=str(e),
                success=False
            ))
    else:
        logger.info("FeatureExtrusion3 接口未暴露，正在平滑回退 FeatureExtrusion2...")
        GLOBAL_DEGRADATION_LOG.append(DegradationEvent(
            timestamp=time.time(),
            feature="extrude_boss",
            target_version=current_year,
            primary_api="FeatureExtrusion3",
            fallback_api="FeatureExtrusion2",
            reason="FeatureExtrusion3 not found on FeatureManager",
            success=False
        ))

    # 回退到 FeatureExtrusion2 (19 参数旧版签名)
    extrude2 = getattr(feat_mgr, "FeatureExtrusion2", None)
    if callable(extrude2):
        try:
            feat = extrude2(
                single_dir, flip, direction, termination1, termination2,
                depth1, depth2, draft_both, draft1, draft2,
                draft_angle1, draft_angle2, draft_outward1, draft_outward2,
                False, False, False, merge, use_feature_scope
            )
            if feat:
                if GLOBAL_DEGRADATION_LOG and GLOBAL_DEGRADATION_LOG[-1].feature == "extrude_boss":
                    GLOBAL_DEGRADATION_LOG[-1].success = True
                return feat
        except Exception as e:
            if not is_com_interface_mismatch_error(e):
                raise
            logger.warning(f"FeatureExtrusion2 回退调用失败: {e}")

    raise SolidWorksCompatError(
        "当前 SolidWorks 版本无法调用拉伸凸台接口 (FeatureExtrusion3/2)，请检查 CAD 安装或草图选区合法性。",
        version=current_year,
        feature="FeatureExtrusion",
        degradation_attempted=True
    )


def safe_extrude_cut(
    feat_mgr: Any,
    single_dir: bool = True,
    flip: bool = False,
    direction: bool = True,
    termination1: int = 0,
    termination2: int = 0,
    depth1: float = 0.01,
    depth2: float = 0.0,
    draft_both: bool = False,
    draft1: bool = False,
    draft2: bool = False,
    draft_angle1: float = 0.0,
    draft_angle2: float = 0.0,
    draft_outward1: bool = False,
    draft_outward2: bool = False,
    normal_cut: bool = False,
    use_feature_scope: bool = False,
    use_auto_select: bool = True,
    assembly_feature_scope: bool = False,
    auto_select_components: bool = False,
    propagate_to_parts: bool = False,
    current_year: Optional[int] = None
) -> Any:
    """
    多版本拉伸切除调度：
    1. 首选 FeatureCut4 (27 参数完整签名)，内建反向自愈。
    2. 若触发接口缺失或参数不匹配，回退至 FeatureCut3 (21 参数旧版签名)。
    3. 严禁把几何穿透失败或草图自交误判为接口缺失。
    """
    cut4 = getattr(feat_mgr, "FeatureCut4", None)
    if callable(cut4):
        try:
            feat = cut4(
                single_dir, bool(flip), bool(direction),
                termination1, termination2, depth1, depth2,
                draft_both, draft1, draft2,
                draft_angle1, draft_angle2, draft_outward1, draft_outward2,
                False, False, False, False, bool(normal_cut),
                bool(use_feature_scope), bool(use_auto_select),
                bool(assembly_feature_scope), bool(auto_select_components),
                bool(propagate_to_parts), 0, 0, False
            )
            if feat:
                return feat
            # 方向自愈重试
            feat = cut4(
                single_dir, bool(flip), not bool(direction),
                termination1, termination2, depth1, depth2,
                draft_both, draft1, draft2,
                draft_angle1, draft_angle2, draft_outward1, draft_outward2,
                False, False, False, False, bool(normal_cut),
                bool(use_feature_scope), bool(use_auto_select),
                bool(assembly_feature_scope), bool(auto_select_components),
                bool(propagate_to_parts), 0, 0, False
            )
            if feat:
                return feat
        except Exception as e:
            if not is_com_interface_mismatch_error(e):
                raise
            logger.info(f"FeatureCut4 接口缺失/签名不匹配 ({e})，正在回退至 FeatureCut3...")
            GLOBAL_DEGRADATION_LOG.append(DegradationEvent(
                timestamp=time.time(),
                feature="extrude_cut",
                target_version=current_year,
                primary_api="FeatureCut4",
                fallback_api="FeatureCut3",
                reason=str(e),
                success=False
            ))
    else:
        logger.info("FeatureCut4 接口未暴露，正在回退至 FeatureCut3...")
        GLOBAL_DEGRADATION_LOG.append(DegradationEvent(
            timestamp=time.time(),
            feature="extrude_cut",
            target_version=current_year,
            primary_api="FeatureCut4",
            fallback_api="FeatureCut3",
            reason="FeatureCut4 not found on FeatureManager",
            success=False
        ))

    # 回退到 FeatureCut3 (21 参数旧版签名)
    cut3 = getattr(feat_mgr, "FeatureCut3", None)
    if callable(cut3):
        try:
            feat = cut3(
                single_dir, bool(flip), bool(direction),
                termination1, termination2, depth1, depth2,
                draft_both, draft1, draft2,
                draft_angle1, draft_angle2, draft_outward1, draft_outward2,
                False, False, False, False, bool(normal_cut),
                bool(use_feature_scope), bool(use_auto_select)
            )
            if feat:
                if GLOBAL_DEGRADATION_LOG and GLOBAL_DEGRADATION_LOG[-1].feature == "extrude_cut":
                    GLOBAL_DEGRADATION_LOG[-1].success = True
                return feat
            # 同样保持切除方向反向自愈
            feat = cut3(
                single_dir, bool(flip), not bool(direction),
                termination1, termination2, depth1, depth2,
                draft_both, draft1, draft2,
                draft_angle1, draft_angle2, draft_outward1, draft_outward2,
                False, False, False, False, bool(normal_cut),
                bool(use_feature_scope), bool(use_auto_select)
            )
            if feat:
                if GLOBAL_DEGRADATION_LOG and GLOBAL_DEGRADATION_LOG[-1].feature == "extrude_cut":
                    GLOBAL_DEGRADATION_LOG[-1].success = True
                return feat
        except Exception as e:
            if not is_com_interface_mismatch_error(e):
                raise
            logger.warning(f"FeatureCut3 回退调用失败: {e}")

    raise SolidWorksCompatError(
        "当前 SolidWorks 版本无法调用拉伸切除接口 (FeatureCut4/3)，请确认切除几何是否与实体相交。",
        version=current_year,
        feature="FeatureCut",
        degradation_attempted=True
    )


def safe_mirror_feature(
    feat_mgr: Any,
    mirror_plane_selected: bool = True,
    geometry_pattern: bool = False,
    knit_surfaces: bool = False,
    reverse_direction: bool = False,
    feature_scope: int = 0,
    current_year: Optional[int] = None
) -> Any:
    """
    多版本镜像特征调度：
    首选 InsertMirrorFeature2；缺失时平滑降级至 InsertMirrorFeature。
    """
    mirror2 = getattr(feat_mgr, "InsertMirrorFeature2", None)
    if callable(mirror2):
        try:
            feat = mirror2(geometry_pattern, knit_surfaces, reverse_direction, False, feature_scope)
            if feat:
                return feat
        except Exception as e:
            if not is_com_interface_mismatch_error(e):
                raise
            logger.info(f"InsertMirrorFeature2 接口缺失 ({e})，正在回退至 InsertMirrorFeature...")
            GLOBAL_DEGRADATION_LOG.append(DegradationEvent(
                timestamp=time.time(),
                feature="mirror_feature",
                target_version=current_year,
                primary_api="InsertMirrorFeature2",
                fallback_api="InsertMirrorFeature",
                reason=str(e),
                success=False
            ))
    else:
        logger.info("InsertMirrorFeature2 接口未暴露，正在回退至 InsertMirrorFeature...")
        GLOBAL_DEGRADATION_LOG.append(DegradationEvent(
            timestamp=time.time(),
            feature="mirror_feature",
            target_version=current_year,
            primary_api="InsertMirrorFeature2",
            fallback_api="InsertMirrorFeature",
            reason="InsertMirrorFeature2 not found on FeatureManager",
            success=False
        ))

    mirror1 = getattr(feat_mgr, "InsertMirrorFeature", None)
    if callable(mirror1):
        try:
            feat = None
            try:
                feat = mirror1(geometry_pattern, knit_surfaces, reverse_direction, False)
            except Exception as e4:
                if is_com_interface_mismatch_error(e4):
                    feat = mirror1(geometry_pattern, knit_surfaces, reverse_direction)
                else:
                    raise
            if feat:
                if GLOBAL_DEGRADATION_LOG and GLOBAL_DEGRADATION_LOG[-1].feature == "mirror_feature":
                    GLOBAL_DEGRADATION_LOG[-1].success = True
                return feat
        except Exception as e:
            if not is_com_interface_mismatch_error(e):
                raise
            logger.warning(f"InsertMirrorFeature 回退失败: {e}")

    raise SolidWorksCompatError(
        "当前 SolidWorks 版本无法调用镜像特征接口 (InsertMirrorFeature2/1)，请检查镜像基准面与特征选择。",
        version=current_year,
        feature="InsertMirrorFeature",
        degradation_attempted=True
    )


def safe_mass_properties(model: Any, current_year: Optional[int] = None) -> Dict[str, float]:
    """
    多版本质量属性提取：
    首选高精度 Extension.CreateMassProperty；
    不可用或处于轻量只读状态时，平滑回退至 Extension.GetMassProperties2 数组解析。
    """
    result = {
        "mass_kg": 0.0,
        "volume_m3": 0.0,
        "surface_area_m2": 0.0,
        "center_of_mass_x": 0.0,
        "center_of_mass_y": 0.0,
        "center_of_mass_z": 0.0,
    }

    if not model:
        return result

    # 1. 尝试 Extension.CreateMassProperty
    try:
        from sw_connect import get_com_member
        ext = get_com_member(model, "Extension")
        if ext and hasattr(ext, "CreateMassProperty"):
            mp = get_com_member(ext, "CreateMassProperty")
            if mp:
                result["mass_kg"] = float(get_com_member(mp, "Mass") or 0.0)
                result["volume_m3"] = float(get_com_member(mp, "Volume") or 0.0)
                result["surface_area_m2"] = float(get_com_member(mp, "SurfaceArea") or 0.0)
                com = get_com_member(mp, "CenterOfMass")
                if com and len(com) >= 3:
                    result["center_of_mass_x"] = float(com[0])
                    result["center_of_mass_y"] = float(com[1])
                    result["center_of_mass_z"] = float(com[2])
                return result
    except Exception as e:
        logger.debug(f"CreateMassProperty 调用失败，回退旧版属性接口: {e}")

    # 2. 回退到 GetMassProperties2 (返回 6 元素或以上浮点数组)
    try:
        from sw_connect import get_com_member
        ext = get_com_member(model, "Extension")
        if ext and hasattr(ext, "GetMassProperties2"):
            props = None
            for try_args in [(1, 0, False), (1, 0), (1,), ()]:
                try:
                    props = ext.GetMassProperties2(*try_args)
                    if props and len(props) >= 6:
                        break
                except Exception:
                    pass
            if props and len(props) >= 6:
                result["center_of_mass_x"] = float(props[0])
                result["center_of_mass_y"] = float(props[1])
                result["center_of_mass_z"] = float(props[2])
                result["volume_m3"] = float(props[3])
                result["surface_area_m2"] = float(props[4])
                result["mass_kg"] = float(props[5])
                return result
    except Exception as e:
        logger.debug(f"GetMassProperties2 回退失败: {e}")

    return result


def safe_add_mate(
    asm_doc: Any,
    mate_type: int,
    align: int,
    flip: bool,
    distance: float,
    distance_upper: float,
    distance_lower: float,
    gear_ratio_num: float,
    gear_ratio_den: float,
    angle: float,
    angle_upper: float,
    angle_lower: float,
    for_positioning_only: bool,
    lock_rotation: bool,
    width_option: int,
    error_status: Any,
    current_year: Optional[int] = None
) -> Any:
    """
    多版本装配体配合创建调度：
    首选 AddMate5 (15 参数现代接口)；缺失时平滑回退至 AddMate3 (14 参数) / CreateMate。
    """
    add_mate5 = getattr(asm_doc, "AddMate5", None)
    if callable(add_mate5):
        try:
            return add_mate5(
                mate_type, align, flip, distance, distance_upper, distance_lower,
                gear_ratio_num, gear_ratio_den, angle, angle_upper, angle_lower,
                for_positioning_only, lock_rotation, width_option, error_status
            )
        except Exception as e:
            if not is_com_interface_mismatch_error(e):
                raise
            logger.info(f"AddMate5 接口缺失 ({e})，正在回退至 AddMate3...")
            GLOBAL_DEGRADATION_LOG.append(DegradationEvent(
                timestamp=time.time(),
                feature="add_mate",
                target_version=current_year,
                primary_api="AddMate5",
                fallback_api="AddMate3",
                reason=str(e),
                success=False
            ))
    else:
        logger.info("AddMate5 接口未暴露，正在回退至 AddMate3...")
        GLOBAL_DEGRADATION_LOG.append(DegradationEvent(
            timestamp=time.time(),
            feature="add_mate",
            target_version=current_year,
            primary_api="AddMate5",
            fallback_api="AddMate3",
            reason="AddMate5 not found on AssemblyDoc",
            success=False
        ))

    add_mate3 = getattr(asm_doc, "AddMate3", None)
    if callable(add_mate3):
        try:
            # AddMate3 缺少末尾的 width_option 参数
            feat = add_mate3(
                mate_type, align, flip, distance, distance_upper, distance_lower,
                gear_ratio_num, gear_ratio_den, angle, angle_upper, angle_lower,
                for_positioning_only, lock_rotation, error_status
            )
            if feat and GLOBAL_DEGRADATION_LOG and GLOBAL_DEGRADATION_LOG[-1].feature == "add_mate":
                GLOBAL_DEGRADATION_LOG[-1].success = True
            return feat
        except Exception as e:
            if not is_com_interface_mismatch_error(e):
                raise
            logger.warning(f"AddMate3 回退失败: {e}")

    raise SolidWorksCompatError(
        "当前 SolidWorks 版本无法调用装配体配合接口 (AddMate5/3)，请确认装配基准面与选择集状态。",
        version=current_year,
        feature="AddMate",
        degradation_attempted=True
    )


def safe_create_drawing_view(
    draw_doc: Any,
    model_path: str,
    view_name: str,
    center_x: float,
    center_y: float,
    center_z: float = 0.0,
    current_year: Optional[int] = None
) -> Any:
    """
    多版本工程图投影视图创建调度：
    首选 CreateDrawViewFromModelView3；缺失时回退至 CreateDrawViewFromModelView2。
    """
    create3 = getattr(draw_doc, "CreateDrawViewFromModelView3", None)
    if callable(create3):
        try:
            return create3(model_path, view_name, center_x, center_y, center_z)
        except Exception as e:
            if not is_com_interface_mismatch_error(e):
                raise
            logger.info(f"CreateDrawViewFromModelView3 接口缺失 ({e})，正在回退至 CreateDrawViewFromModelView2...")
            GLOBAL_DEGRADATION_LOG.append(DegradationEvent(
                timestamp=time.time(),
                feature="create_drawing_view",
                target_version=current_year,
                primary_api="CreateDrawViewFromModelView3",
                fallback_api="CreateDrawViewFromModelView2",
                reason=str(e),
                success=False
            ))
    else:
        logger.info("CreateDrawViewFromModelView3 接口未暴露，正在回退至 CreateDrawViewFromModelView2...")
        GLOBAL_DEGRADATION_LOG.append(DegradationEvent(
            timestamp=time.time(),
            feature="create_drawing_view",
            target_version=current_year,
            primary_api="CreateDrawViewFromModelView3",
            fallback_api="CreateDrawViewFromModelView2",
            reason="CreateDrawViewFromModelView3 not found on DrawingDoc",
            success=False
        ))

    create2 = getattr(draw_doc, "CreateDrawViewFromModelView2", None)
    if callable(create2):
        try:
            feat = create2(model_path, view_name, center_x, center_y, center_z)
            if feat and GLOBAL_DEGRADATION_LOG and GLOBAL_DEGRADATION_LOG[-1].feature == "create_drawing_view":
                GLOBAL_DEGRADATION_LOG[-1].success = True
            return feat
        except Exception as e:
            if not is_com_interface_mismatch_error(e):
                raise
            logger.warning(f"CreateDrawViewFromModelView2 回退失败: {e}")

    raise SolidWorksCompatError(
        "当前 SolidWorks 版本无法调用工程图视图创建接口 (CreateDrawViewFromModelView3/2)，请确认模型路径与视图名称。",
        version=current_year,
        feature="CreateDrawView",
        degradation_attempted=True
    )
