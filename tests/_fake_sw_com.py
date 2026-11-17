# -*- coding: utf-8 -*-
"""
[MOCK-COM] L3 离线 SolidWorks COM 几何与文档状态机仿真器 (`tests/_fake_sw_com.py`)。

设计说明：
- 当本地未运行实机 `SLDWORKS.exe` 时，为端到端/故障注入/阶段验收套件提供确定性的 L3 Fake-COM 仿真环境，
  避免测试套件出现 `Ran 0 tests` 或 `skipped=1` 的虚假跳过。
- 所有启用本仿真器的测试均显式打印 `[MOCK-COM]` 标记，绝不冒充 L5 实机 COM 物理证据。
"""
from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any, Dict, List, Optional


class FakeFeature:
    def __init__(self, model: "FakeModelDoc", name: str, ftype: str, volume_delta_m3: float = 0.0, bbox_m: Optional[tuple] = None):
        self._model = model
        self.Name = name
        self._type = ftype
        self.volume_delta_m3 = float(volume_delta_m3)
        self.bbox_m = bbox_m
        self._next: Optional["FakeFeature"] = None

    def GetTypeName2(self) -> str:
        return self._type

    def GetTypeName(self) -> str:
        return self._type

    def GetNextFeature(self) -> Optional["FakeFeature"]:
        return self._next

    def GetFirstSubFeature(self):
        return None

    def GetErrorCode2(self):
        return (0, False)

    def Select2(self, append: bool = False, mark: int = 0) -> bool:
        if not append:
            self._model._selected_features.clear()
        self._model._selected_features.append(self.Name)
        return True

    def GetSpecificFeature2(self):
        return self

    def GetConstrainedStatus(self) -> int:
        return 3

    @property
    def RelationManager(self):
        class _FakeDim:
            def GetNameForSelection(inner_self) -> str:
                return f"D1@{self.Name}"

        class _FakeRel:
            def GetRelationType(inner_self) -> int:
                return 1

            def GetDisplayDimension(inner_self):
                return _FakeDim()

        class _FakeRelMgr:
            def GetRelations(inner_self, _filter: int = 0):
                return [_FakeRel()]

        return _FakeRelMgr()


class FakeMassProperty:
    def __init__(self, model: "FakeModelDoc"):
        self._model = model
        self.UseSystemUnits = True

    @property
    def Volume(self) -> float:
        return max(0.0, sum(f.volume_delta_m3 for f in self._model._features))

    @property
    def SurfaceArea(self) -> float:
        vol = self.Volume
        return 0.02 if vol > 0 else 0.0

    @property
    def Mass(self) -> float:
        return self.Volume * 7800.0

    @property
    def CenterOfMass(self):
        return (0.0, 0.0, 0.0)

    def GetMomentOfInertia(self, _coord: int = 0):
        return (0.0,) * 9


class FakeExtension:
    def __init__(self, model: "FakeModelDoc"):
        self._model = model

    def SelectByID2(self, name: str, sel_type: str, x: float, y: float, z: float, append: bool, mark: int, callout: Any, align: int) -> bool:
        if sel_type == "EXTSKETCHPOINT" or "@Origin" in str(name) or "@原点" in str(name):
            return True
        feat = self._model.FeatureByName(str(name))
        if feat is not None:
            feat.Select2(append, mark)
            return True
        return False

    def DeleteSelection2(self, _options: int = 0) -> bool:
        return self._model.EditDelete()

    def CreateMassProperty(self) -> FakeMassProperty:
        return FakeMassProperty(self._model)

    def CreateMassProperty2(self) -> FakeMassProperty:
        return FakeMassProperty(self._model)

    def SaveAs(self, file_path: str, *_args) -> bool:
        return self._model._write_disk_file(file_path)

    def SaveAs3(self, file_path: str, *_args) -> int:
        return 0 if self._model._write_disk_file(file_path) else 1


class FakeSketchManager:
    def __init__(self, model: "FakeModelDoc"):
        self._model = model
        self.ActiveSketch: Optional[FakeFeature] = None
        self._last_profile_area_m2: float = 0.0
        self._last_profile_bbox_m: Optional[tuple] = None

    def InsertSketch(self, _update_edit_rebuild: bool = True):
        if self.ActiveSketch is None:
            idx = self._model._next_counter("Sketch")
            sk = self._model._append_feature(f"Sketch{idx}", "ProfileFeature", 0.0)
            self.ActiveSketch = sk
            return sk
        else:
            finished = self.ActiveSketch
            self.ActiveSketch = None
            return finished

    def CreateCornerRectangle(self, x1: float, y1: float, z1: float, x2: float, y2: float, z2: float):
        w = abs(float(x2) - float(x1))
        h = abs(float(y2) - float(y1))
        self._last_profile_area_m2 = w * h
        self._last_profile_bbox_m = (min(x1, x2), min(y1, y2), 0.0, max(x1, x2), max(y1, y2), 0.0)
        return ["Line1", "Line2", "Line3", "Line4"]

    def CreateCenterRectangle(self, cx: float, cy: float, cz: float, x2: float, y2: float, z2: float):
        w = 2.0 * abs(float(x2) - float(cx))
        h = 2.0 * abs(float(y2) - float(cy))
        self._last_profile_area_m2 = w * h
        self._last_profile_bbox_m = (cx - w / 2, cy - h / 2, 0.0, cx + w / 2, cy + h / 2, 0.0)
        return ["Line1", "Line2", "Line3", "Line4"]

    def CreateCircleByRadius(self, cx: float, cy: float, cz: float, radius: float):
        r = abs(float(radius))
        self._last_profile_area_m2 = math.pi * (r ** 2)
        return ("Arc1",)

    def CreateCircle(self, cx: float, cy: float, cz: float, px: float, py: float, pz: float):
        r = math.hypot(float(px) - float(cx), float(py) - float(cy))
        self._last_profile_area_m2 = math.pi * (r ** 2)
        return ("Arc1",)

    def FullyDefineSketch(self, *_args) -> int:
        return 0


class FakeFeatureManager:
    def __init__(self, model: "FakeModelDoc"):
        self._model = model

    def InsertRefPlane(self, *_args):
        idx = self._model._next_counter("Plane")
        return self._model._append_feature(f"Plane{idx}", "RefPlane", 0.0)

    def FeatureExtrusion3(self, sd: bool, flip: bool, dir_flag: bool, t1: int, t2: int, d1: float, d2: float, *_rest):
        return self._extrude_boss(d1)

    def FeatureExtrusion2(self, sd: bool, flip: bool, dir_flag: bool, t1: int, t2: int, d1: float, d2: float, *_rest):
        return self._extrude_boss(d1)

    def _extrude_boss(self, depth_m: float):
        d = float(depth_m)
        if d <= 0.0:
            return None
        self._model.SketchManager.ActiveSketch = None
        area = self._model.SketchManager._last_profile_area_m2 or (0.05 * 0.05)
        vol = area * d
        bbox = self._model.SketchManager._last_profile_bbox_m
        if bbox is not None:
            bbox3d = (bbox[0], bbox[1], 0.0, bbox[3], bbox[4], d)
        else:
            bbox3d = (0.0, 0.0, 0.0, 0.1, 0.06, d)
        idx = self._model._next_counter("Boss-Extrude")
        return self._model._append_feature(f"Boss-Extrude{idx}", "Extrude", vol, bbox_m=bbox3d)

    def FeatureCut4(self, sd: bool, flip: bool, dir_flag: bool, t1: int, t2: int, d1: float, d2: float, *_rest):
        return self._extrude_cut(d1)

    def FeatureCut3(self, sd: bool, flip: bool, dir_flag: bool, t1: int, t2: int, d1: float, d2: float, *_rest):
        return self._extrude_cut(d1)

    def _extrude_cut(self, depth_m: float):
        d = float(depth_m)
        if d <= 0.0:
            return None
        self._model.SketchManager.ActiveSketch = None
        area = self._model.SketchManager._last_profile_area_m2 or (math.pi * (0.01 ** 2))
        boss_depths = [
            abs(f.bbox_m[5] - f.bbox_m[2])
            for f in self._model._features
            if f.volume_delta_m3 > 0 and f.bbox_m is not None
        ]
        effective_d = min(d, max(boss_depths)) if boss_depths else d
        vol = -area * effective_d
        idx = self._model._next_counter("Cut-Extrude")
        return self._model._append_feature(f"Cut-Extrude{idx}", "ICE", vol)


class FakeBody:
    def GetType(self) -> int:
        return 0


class FakeModelDoc:
    def __init__(self, app: "FakeSwApp", title: str, doc_type: int = 1, path: str = ""):
        self._app = app
        self._title = title
        self._doc_type = doc_type
        self._path = path
        self._counters: Dict[str, int] = {}
        self._features: List[FakeFeature] = []
        self._selected_features: List[str] = []
        self.Extension = FakeExtension(self)
        self.SketchManager = FakeSketchManager(self)
        self.FeatureManager = FakeFeatureManager(self)
        for std_plane in ("前视基准面", "上视基准面", "右视基准面", "Front Plane", "Top Plane", "Right Plane", "Origin"):
            self._append_feature(std_plane, "RefPlane" if "Origin" not in std_plane else "OriginProfileFeature", 0.0)

    def _next_counter(self, prefix: str) -> int:
        val = self._counters.get(prefix, 0) + 1
        self._counters[prefix] = val
        return val

    def _append_feature(self, name: str, ftype: str, volume_delta_m3: float, bbox_m: Optional[tuple] = None) -> FakeFeature:
        feat = FakeFeature(self, name, ftype, volume_delta_m3, bbox_m=bbox_m)
        if self._features:
            self._features[-1]._next = feat
        self._features.append(feat)
        return feat

    def _relink_features(self) -> None:
        for idx, feat in enumerate(self._features):
            feat._next = self._features[idx + 1] if idx + 1 < len(self._features) else None

    def GetTitle(self) -> str:
        return self._title

    def GetPathName(self) -> str:
        return self._path

    def GetType(self) -> int:
        return self._doc_type

    def FirstFeature(self) -> Optional[FakeFeature]:
        return self._features[0] if self._features else None

    def FeatureByName(self, name: str) -> Optional[FakeFeature]:
        for f in self._features:
            if f.Name == name:
                return f
        return None

    def ClearSelection2(self, _all: bool = True) -> bool:
        self._selected_features.clear()
        return True

    def EditDelete(self) -> bool:
        if not self._selected_features:
            return False
        targets = set(self._selected_features)
        before_len = len(self._features)
        self._features = [f for f in self._features if f.Name not in targets]
        self._relink_features()
        self._selected_features.clear()
        return len(self._features) < before_len

    def EditRebuild3(self) -> bool:
        return True

    def ForceRebuild3(self, _top_only: bool = False) -> bool:
        return True

    def GetPartBox(self, _no_hidden: bool = True):
        for f in reversed(self._features):
            if f.bbox_m is not None:
                return f.bbox_m
        return (0.0, 0.0, 0.0, 0.1, 0.06, 0.02)

    def GetBodies2(self, _body_type: int = 0, _visible_only: bool = False):
        has_solid = sum(f.volume_delta_m3 for f in self._features) > 0
        return [FakeBody()] if has_solid else []

    def GetSaveFlag(self) -> bool:
        return False

    def SetSaveFlag(self) -> None:
        return None

    def SetMaterialPropertyValues2(self, *_args) -> None:
        return None

    def Save3(self, *_args) -> int:
        if self._path:
            self._write_disk_file(self._path)
            return 0
        return 1

    def SaveAs(self, file_path: str) -> int:
        return 0 if self._write_disk_file(file_path) else 1

    def SaveAs3(self, file_path: str, *_args) -> int:
        return 0 if self._write_disk_file(file_path) else 1

    def _write_disk_file(self, file_path: str) -> bool:
        p = Path(file_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"FAKE-SLDPRT-MOCK-COM")
        self._path = str(p.resolve())
        self._title = p.name
        return True


class FakeSwApp:
    def __init__(self):
        self._docs: List[FakeModelDoc] = []
        self._doc_seq = 0
        self.Visible = True
        self.CommandInProgress = False

    def RevisionNumber(self) -> str:
        return "34.0.0"

    def GetProcessID(self) -> int:
        return os.getpid()

    @property
    def ActiveDoc(self) -> Optional[FakeModelDoc]:
        return self._docs[-1] if self._docs else None

    def GetDocuments(self) -> List[FakeModelDoc]:
        return list(self._docs)

    def GetDocumentCount(self) -> int:
        return len(self._docs)

    def GetFirstDocument(self):
        return self._docs[0] if self._docs else None

    def GetOpenDocumentByName(self, path_or_name: str) -> Optional[FakeModelDoc]:
        target_norm = os.path.normcase(os.path.abspath(str(path_or_name)))
        target_base = os.path.normcase(os.path.basename(str(path_or_name)))
        for d in self._docs:
            if d._path and os.path.normcase(os.path.abspath(d._path)) == target_norm:
                return d
            if os.path.normcase(d._title) == target_base:
                return d
        return None

    def NewDocument(self, _template: str, _paper: int, _w: float, _h: float) -> FakeModelDoc:
        self._doc_seq += 1
        doc = FakeModelDoc(self, f"Part{self._doc_seq}")
        self._docs.append(doc)
        return doc

    def ActivateDoc3(self, name: str, *_args):
        doc = self.GetOpenDocumentByName(name)
        if doc is not None and doc in self._docs:
            self._docs.remove(doc)
            self._docs.append(doc)
        return doc

    def CloseDoc(self, name_or_path: str) -> bool:
        target = str(name_or_path or "").strip()
        if not target:
            return False
        target_base = os.path.normcase(os.path.basename(target))
        target_no_ext = os.path.normcase(os.path.splitext(target_base)[0])
        for d in list(self._docs):
            d_title = os.path.normcase(d._title)
            d_no_ext = os.path.normcase(os.path.splitext(d._title)[0])
            d_path = os.path.normcase(os.path.abspath(d._path)) if d._path else ""
            if d_title == target_base or d_no_ext == target_no_ext or (d_path and d_path == os.path.normcase(os.path.abspath(target))):
                self._docs.remove(d)
                return True
        return False


_FAKE_APP_SINGLETON: Optional[FakeSwApp] = None


def ensure_fake_solidworks_env() -> FakeSwApp:
    """当未运行真实 SolidWorks 时挂载 FakeSwApp，返回实例。"""
    global _FAKE_APP_SINGLETON
    if _FAKE_APP_SINGLETON is None:
        _FAKE_APP_SINGLETON = FakeSwApp()
    app = _FAKE_APP_SINGLETON

    import sw_connect
    import sw_process

    print("[MOCK-COM] 未检测到运行中的实机 SolidWorks，启用 L3 Fake-COM 仿真验证（非 L5 实机证据）")

    def _fake_connect_solidworks(version=None, wait_seconds=5, visible=True, return_metadata=False, target_pid=None, allow_launch=None):
        model = app.ActiveDoc
        meta = {
            "prog_id": "SldWorks.Application.34",
            "requested_version": version,
            "started_by_cad_studio": False,
            "actual_version": 2026,
            "actual_revision": "34.0.0",
            "process_id": app.GetProcessID(),
            "process_create_time": 0.0,
            "mock_com": True,
        }
        return (app, model, meta) if return_metadata else (app, model)

    def _fake_new_document(sw_obj, doc_type="part", template_path=None, *, max_documents=None):
        target_sw = sw_obj or app
        doc = target_sw.NewDocument(template_path or "part.prtdot", 0, 0.0, 0.0)
        sw_connect.register_owned_document(doc)
        return doc

    sw_connect.connect_solidworks = _fake_connect_solidworks
    sw_connect.new_document = _fake_new_document
    sw_connect.solidworks_processes = lambda: {app.GetProcessID(): 2026}
    sw_process.list_solidworks_instances = lambda: [{
        "pid": app.GetProcessID(),
        "year": 2026,
        "exe_path": "MOCK_COM_SLDWORKS.exe",
        "responding": True,
    }]

    try:
        import importlib
        scripts_connect = importlib.import_module("scripts.sw_connect")
        scripts_connect.connect_solidworks = _fake_connect_solidworks
        scripts_connect.new_document = _fake_new_document
        scripts_connect.solidworks_processes = sw_connect.solidworks_processes
    except Exception:
        pass

    try:
        import server
        server._load_automation_modules()
        server.connect_solidworks = _fake_connect_solidworks
        server.new_document = _fake_new_document
    except Exception:
        pass

    return app
