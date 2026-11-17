"""@brief 原生阵列的参数和选择适配，复用 B-Rep 选边，不增加用户入口。"""
from __future__ import annotations

import math

try:
    from .sw_connect import create_empty_dispatch_variant, get_com_member
    from .sw_edge_select import iter_model_edges
except ImportError:
    from sw_connect import create_empty_dispatch_variant, get_com_member
    from sw_edge_select import iter_model_edges


def _unit(vector):
    """@brief 检查并归一化方向；方向不是长度参数。"""
    values = tuple(float(value) for value in vector)
    if len(values) != 3:
        raise ValueError("阵列方向必须有三个分量")
    length = math.sqrt(sum(value * value for value in values))
    if not all(math.isfinite(value) for value in values) or length < 1e-12:
        raise ValueError("阵列方向必须是非零有限向量")
    return tuple(value / length for value in values)


def _seed(model, name):
    """@brief 精确选择母特征，失败立即停止。"""
    feature = get_com_member(model, "FeatureByName", str(name))
    if feature is None or not bool(get_com_member(feature, "Select2", False, 4)):
        raise ValueError(f"无法选择阵列母特征: {name}")


def _select_entity(model, entity, mark, append=True):
    """@brief 使用带 Mark 的 ISelectData 选择实体，保留失败事实。"""
    data = get_com_member(model.SelectionManager, "CreateSelectData")
    data.Mark = int(mark)
    return bool(get_com_member(entity, "Select4", append, data))


def _direction(model, vector, mark):
    """@brief 相同方向的平行直边语义等价，确定性选择其中一条。"""
    requested = _unit(vector)
    descriptors, _ = iter_model_edges(model)
    candidates = []
    for item in descriptors:
        direction = item.get("direction")
        if item.get("is_line") is not True or direction is None:
            continue
        dot = sum(a * b for a, b in zip(requested, direction))
        if abs(dot) >= 1 - 1e-8:
            candidates.append((item, dot))
    candidates.sort(key=lambda pair: (-(pair[0].get("length_mm") or 0), pair[0]["index"]))
    for item, dot in candidates:
        try:
            selected = _select_entity(model, item["edge"], mark)
        except Exception:
            selected = False
        if selected:
            return dot < 0
    raise ValueError(f"找不到可选的阵列方向直边: {requested}")


def linear_pattern(model, feature_name, first, spacing, count, second=(0, 0, 0), second_spacing=0, second_count=1):
    """@brief 创建 20 参数 FeatureLinearPattern4；旧版本仅在成员缺失时用 10 参数路径。
    @param model 原生零件文档。
    @param first 第一方向向量。
    @param spacing 间距，单位米。
    @param count 包括母特征的实例数量。
    @return IFeature；空返回按执行失败抛出异常。
    """
    if int(count) < 2 or int(second_count) < 1 or not math.isfinite(float(spacing)) or spacing <= 0:
        raise ValueError("阵列数量或间距无效")
    if second_count > 1 and (not math.isfinite(float(second_spacing)) or second_spacing <= 0):
        raise ValueError("第二方向间距无效")
    model.ClearSelection2(True)
    try:
        _seed(model, feature_name)
        flip1 = _direction(model, first, 1)
        flip2 = _direction(model, second, 2) if second_count > 1 else False
        args = (int(count), float(spacing), int(second_count), float(second_spacing),
                flip1, flip2, "", "", False, False)
        method = getattr(model.FeatureManager, "FeatureLinearPattern4", None)
        if method is not None:
            feature = method(*args, False, False, False, False, False, False, False, False, 0.0, 0.0)
        else:
            feature = model.FeatureManager.FeatureLinearPattern3(*args)
        if feature is None:
            raise RuntimeError("原生线性阵列创建失败")
        return feature
    finally:
        model.ClearSelection2(True)


def _auto_create_or_select_reference_axis(model, axis_spec: str, feature_name: str, mark: int = 1) -> bool:
    """当指定基准轴不存在时，尝试按两正交基准面自动创建基准轴（InsertRefAxis / CreateAxis）并选中 (BUG-012)。"""
    ext = getattr(model, "Extension", None)
    if ext is None:
        return False
    plane_pairs = {
        "z": [("Front Plane", "Right Plane"), ("前视基准面", "右视基准面")],
        "x": [("Front Plane", "Top Plane"), ("前视基准面", "上视基准面")],
        "y": [("Top Plane", "Right Plane"), ("上视基准面", "右视基准面")],
    }
    key = axis_spec.strip().lower()
    candidate_pairs = plane_pairs.get(key, plane_pairs["z"])
    for p1, p2 in candidate_pairs:
        model.ClearSelection2(True)
        s1 = bool(ext.SelectByID2(p1, "PLANE", 0, 0, 0, False, 0, create_empty_dispatch_variant(), 0))
        s2 = bool(ext.SelectByID2(p2, "PLANE", 0, 0, 0, True, 0, create_empty_dispatch_variant(), 0)) if s1 else False
        if not (s1 and s2):
            continue
        created = False
        insert_ref_axis = getattr(model, "InsertRefAxis", None)
        if callable(insert_ref_axis):
            try:
                created = bool(insert_ref_axis(2))
            except Exception:
                created = False
        if not created and hasattr(model, "FeatureManager"):
            fm_axis = getattr(model.FeatureManager, "InsertRefAxis", None) or getattr(model.FeatureManager, "CreateAxis", None)
            if callable(fm_axis):
                try:
                    created = bool(fm_axis(2))
                except Exception:
                    created = False
        if created:
            model.ClearSelection2(True)
            _seed(model, feature_name)
            for candidate_name in (axis_spec, "Axis1", "基准轴1", "Axis2", "基准轴2"):
                if bool(ext.SelectByID2(candidate_name, "AXIS", 0, 0, 0, True, mark, create_empty_dispatch_variant(), 0)):
                    return True
    model.ClearSelection2(True)
    _seed(model, feature_name)
    return False


def circular_pattern(model, feature_name, axis, angle, count, equal_spacing=True):
    """@brief 选择母特征与明确的轴实体（支持缺失时自动通过正交基准面创建基准轴），保留现有 7 参数原生接口。"""
    if int(count) < 2 or not math.isfinite(float(angle)) or not 0 < angle <= 2 * math.pi + 1e-9:
        raise ValueError("圆周阵列数量或角度无效")
    model.ClearSelection2(True)
    try:
        _seed(model, feature_name)
        if isinstance(axis, str):
            selected = bool(model.Extension.SelectByID2(axis, "AXIS", 0, 0, 0, True, 1,
                create_empty_dispatch_variant(), 0))
            if not selected:
                for alias in ("Axis1", "基准轴1") if axis not in ("Axis1", "基准轴1") else ():
                    if bool(model.Extension.SelectByID2(alias, "AXIS", 0, 0, 0, True, 1, create_empty_dispatch_variant(), 0)):
                        selected = True
                        break
            if not selected:
                selected = _auto_create_or_select_reference_axis(model, axis, feature_name, mark=1)
        else:
            selected = _select_entity(model, axis, 1)
        if not selected:
            raise ValueError(f"无法选择圆周阵列轴: {axis}")
        feature = model.FeatureManager.FeatureCircularPattern4(int(count), float(angle), False, "", False, bool(equal_spacing), False)
        if feature is None:
            raise RuntimeError("原生圆周阵列创建失败")
        return feature
    finally:
        model.ClearSelection2(True)
