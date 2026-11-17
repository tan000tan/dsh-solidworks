# -*- coding: utf-8 -*-
"""
tests/r1_strict_boolean_parity_test.py
R1 (AUD-SEC-001) 行为测试：验证后端 Pydantic 模型与 MCP 线协议严格拒绝所有非 JSON Boolean 的布尔字段输入，
杜绝 "y"/"t"/"Y"/"T"/"yes"/"on"/"1"/1 等模糊类型被静默强转为 True 从而触发落盘或启动 SolidWorks。
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parent.parent
SERVER_DIR = REPO_ROOT / "vendor" / "solidworks-automation-skill" / "mcp-server"
SCRIPTS_DIR = REPO_ROOT / "vendor" / "solidworks-automation-skill" / "scripts"
for p in (str(SERVER_DIR), str(SCRIPTS_DIR), str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import server  # noqa: E402


INVALID_BOOL_VALUES = [
    "true",
    "false",
    "True",
    "False",
    "y",
    "Y",
    "t",
    "T",
    "yes",
    "no",
    "on",
    "off",
    "1",
    "0",
    1,
    0,
    None,
    [],
    {},
    [True],
    {"save": True},
]


class TestR1StrictBooleanParity(unittest.TestCase):
    def test_01_four_conditional_save_models_reject_all_non_booleans(self):
        cases = [
            (
                server.SolidWorksDimensionUpdateInput,
                {"dimension_name": "D1@Sketch1", "value_mm": 10.0},
            ),
            (
                server.SolidWorksConfigurationCreateInput,
                {"configuration_name": "CfgA"},
            ),
            (
                server.SolidWorksConfigurationActivateInput,
                {"configuration_name": "Default"},
            ),
            (
                server.SolidWorksCustomPropertiesInput,
                {"properties": {"Material": "Steel"}},
            ),
        ]

        for model_cls, base_kwargs in cases:
            # 合法布尔值与缺省字段必须通过
            m_default = model_cls(**base_kwargs)
            self.assertIs(m_default.save, False)
            m_false = model_cls(**base_kwargs, save=False)
            self.assertIs(m_false.save, False)
            m_true = model_cls(**base_kwargs, save=True)
            self.assertIs(m_true.save, True)

            # 所有非布尔值必须被严格拒绝
            for bad in INVALID_BOOL_VALUES:
                with self.subTest(model=model_cls.__name__, bad=bad):
                    with self.assertRaises(ValidationError):
                        model_cls(**base_kwargs, save=bad)

    def test_02_health_check_start_solidworks_rejects_all_non_booleans(self):
        self.assertIs(server.SolidWorksHealthCheckInput().start_solidworks, False)
        self.assertIs(server.SolidWorksHealthCheckInput(start_solidworks=False).start_solidworks, False)
        self.assertIs(server.SolidWorksHealthCheckInput(start_solidworks=True).start_solidworks, True)
        for bad in INVALID_BOOL_VALUES:
            with self.subTest(bad=bad):
                with self.assertRaises(ValidationError):
                    server.SolidWorksHealthCheckInput(start_solidworks=bad)

    def test_03_mcp_wire_call_rejects_save_y_without_invoking_save(self):
        save_called = False
        orig_save = getattr(server, "save_document", None)

        def _trap_save(*_a, **_kw):
            nonlocal save_called
            save_called = True
            return True

        server.save_document = _trap_save
        try:
            for tool_name, base_params in [
                ("solidworks_update_dimension", {"dimension_name": "D1@Sketch1", "value_mm": 10.0}),
                ("solidworks_create_configuration", {"configuration_name": "CfgA"}),
                ("solidworks_activate_configuration", {"configuration_name": "Default"}),
                ("solidworks_set_custom_properties", {"properties": {"Author": "Test"}}),
            ]:
                for bad in ("y", "t", "Y", "T", "yes", "on", "1", 1, None, [], {}):
                    params = dict(base_params, save=bad)
                    try:
                        res = asyncio.run(server.mcp.call_tool(tool_name, {"params": params}))
                        is_err = getattr(res, "isError", None)
                        if is_err is None:
                            is_err = getattr(res, "is_error", False)
                        self.assertTrue(bool(is_err), f"{tool_name} with save={bad!r} must fail on wire")
                    except Exception:
                        pass
            self.assertFalse(save_called, "Rejected non-boolean save must never reach save_document")
        finally:
            if orig_save is not None:
                server.save_document = orig_save


if __name__ == "__main__":
    unittest.main()
