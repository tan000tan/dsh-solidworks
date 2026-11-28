import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "vendor" / "solidworks-automation-skill" / "scripts"
DRAWING_SCRIPTS_DIR = ROOT / "vendor" / "solidworks-automation-skill" / "subskills" / "solidworks-engineering-drawing" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(DRAWING_SCRIPTS_DIR))

from design_spec import validate_design_spec
from drawing_spec import load_drawing_spec, validate_drawing_spec
from stage5_workflow import inspect_cad_quality, optimize_feature_tree, plan_multi_schemes


class V050RemediationAndStage5Test(unittest.TestCase):
    def test_d09_design_spec_and_drawing_spec_version_compat(self):
        import json
        minimal_design = ROOT / "vendor" / "solidworks-automation-skill" / "templates" / "minimal_design_spec.json"
        self.assertTrue(minimal_design.is_file())
        res_design = validate_design_spec(json.loads(minimal_design.read_text(encoding="utf-8")))
        self.assertEqual(res_design["status"], "ok")

        minimal_drawing = ROOT / "vendor" / "solidworks-automation-skill" / "templates" / "minimal_drawing_spec.json"
        self.assertTrue(minimal_drawing.is_file())
        res_drawing = validate_drawing_spec(str(minimal_drawing))
        self.assertEqual(res_drawing["status"], "pass")

        # Test snake_case schema_version compatibility in drawing_spec
        raw = load_drawing_spec(str(minimal_drawing))
        raw.pop("schemaVersion", None)
        raw["schema_version"] = "1.0"
        res_snake = validate_drawing_spec(raw)
        self.assertEqual(res_snake["status"], "pass")

    def test_stage5_tools_offline(self):
        s = plan_multi_schemes({"part_type": "stepped_shaft", "axisymmetric": True})
        self.assertEqual(s["status"], "ok")
        self.assertEqual(s["recommended_scheme"], "revolve_primary")

        opt = optimize_feature_tree({
            "nodes": [
                {"id": "f1", "type": "fillet"},
                {"id": "e1", "type": "extrude"},
            ]
        })
        self.assertEqual(opt["status"], "ok")
        self.assertTrue(opt["reordered"])
        self.assertEqual(opt["optimized_nodes"][0]["id"], "e1")

        q = inspect_cad_quality({"volume_mm3": 1000.5, "expected_volume_mm3": 1000.0, "failed_features": []})
        self.assertEqual(q["status"], "pass")
        self.assertTrue(q["passed"])


if __name__ == "__main__":
    unittest.main()
