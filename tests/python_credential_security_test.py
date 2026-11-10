"""
Python 凭证安全机制与 8 项反向安全测试 (Negative Security Test Suite)
验证目标：
1. 无凭证 (No credential): theoretical 数据无凭据时降级，不获得权威背书
2. 无效凭证 (Invalid credential): 结构破坏、类型错误、反序列化失败被拦截并记 0 分
3. 过期凭证 (Expired credential): 超出 TTL 的凭据被拦截 (Replay intercept)
4. 被篡改凭证 (Tampered credential): 理论体积/哈希/签名篡改被拦截
5. 同进程重放凭证 (Replay in same process): 相同 Nonce 第二次验证被拦截
6. 跨重启重放凭证 (Replay across simulated restart): 模拟内存重置后，持久化层拦截重用 Nonce
7. 跨独立进程重放凭证 (Replay across separate processes): 独立子进程间共享持久化锁与 Nonce 存储，二次验证被拦截
8. 未授权调用方签发拦截 (Unauthorized authority issuance): 开启权威边界鉴权时，未持合法 key 的签发直接被拒绝
"""

import os
import sys
import time
import copy
import subprocess
import tempfile
import unittest

# 确保脚本和库可导入
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DOCS_SCRIPTS = os.path.join(REPO_ROOT, "docs", "stage5_advanced_ai_cad", "scripts")
if DOCS_SCRIPTS not in sys.path:
    sys.path.insert(0, DOCS_SCRIPTS)

from cad_quality_inspector import (
    CadQualityInspector,
    BenchmarkCredential,
    issue_benchmark_credential,
    verify_benchmark_credential,
    clear_consumed_nonces,
    rotate_benchmark_secret,
    get_benchmark_secret
)

class PythonCredentialSecurityTest(unittest.TestCase):
    def setUp(self):
        # 使用独立的隔离持久化 Nonce 文件，避免测试间干扰
        self.temp_nonce_file = tempfile.mktemp(prefix="dsh_test_nonces_", suffix=".json")
        os.environ["CAD_NONCE_STORE_PATH"] = self.temp_nonce_file
        # 重置私钥与 Nonce
        rotate_benchmark_secret("test_secret_for_security_suite_1234567890")
        clear_consumed_nonces()
        self.inspector = CadQualityInspector()
        self.model_name = "SafetyBracket"
        self.measured_props = {
            "volume_mm3": 25000.0,
            "surface_area_mm2": 8000.0
        }

    def tearDown(self):
        clear_consumed_nonces()
        if os.path.exists(self.temp_nonce_file):
            try:
                os.remove(self.temp_nonce_file)
            except Exception:
                pass
        lock_file = self.temp_nonce_file + ".lock"
        if os.path.exists(lock_file):
            try:
                os.remove(lock_file)
            except Exception:
                pass
        os.environ.pop("CAD_REQUIRE_AUTHORITY_KEY", None)
        os.environ.pop("CAD_AUTHORITY_KEY", None)

    # 1. 无凭据测试 (Fail-Closed: 无凭证时不得给予 VERIFIED 状态，必须降级为 NOT_VERIFIED)
    def test_01_no_credential(self):
        theoretical = {
            "volume_mm3": 25000.0
        }
        report = self.inspector.inspect_quality(
            model_name=self.model_name,
            measured_props=self.measured_props,
            theoretical_props=theoretical
        )
        self.assertIsNotNone(report)
        # 没有经过密码学权威签发的凭证，防御自比对机制必须严格判定为 NOT_VERIFIED
        self.assertEqual(report.geometry_score.status, "NOT_VERIFIED")
        self.assertFalse(report.is_acceptable)
        self.assertNotIn("credential_forgery_detected", report.metrics_summary)

    # 2. 无效凭据测试
    def test_02_invalid_credential(self):
        # 提供损坏的数据结构
        theoretical = {
            "volume_mm3": 25000.0,
            "credential": {
                "issuer": "hacked_authority",
                "model_id": self.model_name
                # 缺少 signature, nonce, hash 等关键字段
            }
        }
        report = self.inspector.inspect_quality(
            model_name=self.model_name,
            measured_props=self.measured_props,
            theoretical_props=theoretical
        )
        self.assertEqual(report.geometry_score.status, "FAILED")
        self.assertEqual(report.geometry_score.score, 0.0)
        self.assertTrue(report.metrics_summary.get("credential_forgery_detected"))

    # 3. 过期凭据测试
    def test_03_expired_credential(self):
        # 签发一个 1 秒前过期的凭据
        cred = issue_benchmark_credential(
            model_id=self.model_name,
            volume_analytical_mm3=25000.0,
            ttl_seconds=-10.0  # 已过期
        )
        valid, reason = verify_benchmark_credential(cred, self.model_name)
        self.assertFalse(valid)
        self.assertIn("expired", reason.lower())

        # 结合 Inspector 检查
        theoretical = {
            "volume_mm3": 25000.0,
            "credential": cred
        }
        report = self.inspector.inspect_quality(
            model_name=self.model_name,
            measured_props=self.measured_props,
            theoretical_props=theoretical
        )
        self.assertEqual(report.geometry_score.status, "FAILED")
        self.assertTrue(report.metrics_summary.get("credential_forgery_detected"))

    # 4. 被篡改的凭据测试
    def test_04_tampered_credential(self):
        cred = issue_benchmark_credential(
            model_id=self.model_name,
            volume_analytical_mm3=25000.0,
            ttl_seconds=300.0
        )
        # 4a. 篡改体积数值
        tampered_cred_dict = cred.model_dump()
        tampered_cred_dict["volume_analytical_mm3"] = 99999.0
        tampered_cred = BenchmarkCredential(**tampered_cred_dict)

        valid, reason = verify_benchmark_credential(tampered_cred, self.model_name)
        self.assertFalse(valid)
        self.assertIn("tampered", reason.lower())

        # 4b. 篡改模型绑定 (跨模型复用攻击)
        cross_model_cred = copy.deepcopy(cred)
        valid2, reason2 = verify_benchmark_credential(cross_model_cred, "OtherBracket")
        self.assertFalse(valid2)
        self.assertIn("mismatch", reason2.lower())

    # 5. 同进程内重复使用的凭据测试
    def test_05_replayed_nonce_same_process(self):
        cred = issue_benchmark_credential(
            model_id=self.model_name,
            volume_analytical_mm3=25000.0,
            ttl_seconds=300.0
        )
        # 第一次验证必须通过
        valid1, reason1 = verify_benchmark_credential(cred, self.model_name)
        self.assertTrue(valid1, f"First verification failed: {reason1}")

        # 第二次验证必须被重放拦截
        valid2, reason2 = verify_benchmark_credential(cred, self.model_name)
        self.assertFalse(valid2)
        self.assertIn("replay attack intercepted", reason2.lower())

    # 6. 跨重启重复使用的凭据测试
    def test_06_replayed_nonce_across_restart(self):
        cred = issue_benchmark_credential(
            model_id=self.model_name,
            volume_analytical_mm3=25000.0,
            ttl_seconds=300.0
        )
        # 进程第一次消费 Nonce
        valid1, reason1 = verify_benchmark_credential(cred, self.model_name)
        self.assertTrue(valid1)

        # 模拟进程重启：只清空内存中的 _CONSUMED_NONCES，保留持久化存储文件
        import cad_quality_inspector
        with cad_quality_inspector._NONCE_LOCK:
            cad_quality_inspector._CONSUMED_NONCES.clear()

        # 验证此时内存确实已空
        self.assertEqual(len(cad_quality_inspector._CONSUMED_NONCES), 0)

        # 重新发起验证，持久化层应当阻断重放
        valid2, reason2 = verify_benchmark_credential(cred, self.model_name)
        self.assertFalse(valid2)
        self.assertIn("replay attack intercepted", reason2.lower())

    # 7. 不同独立子进程之间的重复使用测试
    def test_07_replayed_nonce_across_separate_processes(self):
        cred = issue_benchmark_credential(
            model_id=self.model_name,
            volume_analytical_mm3=25000.0,
            ttl_seconds=300.0
        )
        cred_json = cred.model_dump_json()

        # 脚本 1：在独立 Python 子进程中消费 Nonce
        code_p1 = f"""
import os, sys
sys.path.insert(0, r"{DOCS_SCRIPTS}")
from cad_quality_inspector import BenchmarkCredential, verify_benchmark_credential
cred = BenchmarkCredential.model_validate_json(r'''{cred_json}''')
ok, msg = verify_benchmark_credential(cred, "{self.model_name}")
print(f"P1: {{ok}} - {{msg}}")
sys.exit(0 if ok else 1)
"""
        env = os.environ.copy()
        env["CAD_NONCE_STORE_PATH"] = self.temp_nonce_file
        env["CAD_BENCHMARK_SECRET"] = "test_secret_for_security_suite_1234567890"

        res1 = subprocess.run([sys.executable, "-c", code_p1], env=env, capture_output=True, text=True)
        self.assertEqual(res1.returncode, 0, f"Process 1 failed: {res1.stdout} {res1.stderr}")
        self.assertIn("P1: True", res1.stdout)

        # 脚本 2：在完全不同的第二个 Python 子进程中尝试重放同一个 Nonce
        code_p2 = f"""
import os, sys
sys.path.insert(0, r"{DOCS_SCRIPTS}")
from cad_quality_inspector import BenchmarkCredential, verify_benchmark_credential
cred = BenchmarkCredential.model_validate_json(r'''{cred_json}''')
ok, msg = verify_benchmark_credential(cred, "{self.model_name}")
print(f"P2: {{ok}} - {{msg}}")
sys.exit(0 if ok else 2)
"""
        res2 = subprocess.run([sys.executable, "-c", code_p2], env=env, capture_output=True, text=True)
        # 预期返回码 2 (验证失败)
        self.assertEqual(res2.returncode, 2, f"Process 2 unexpectedly succeeded: {res2.stdout}")
        self.assertIn("replay attack intercepted", res2.stdout.lower())

    # 8. 未授权调用方尝试签发凭据拦截测试
    def test_08_unauthorized_caller_issuance(self):
        os.environ["CAD_REQUIRE_AUTHORITY_KEY"] = "1"
        os.environ["CAD_AUTHORITY_KEY"] = "valid_authority_master_key_9999"

        # 8a: 未提供 authority_key 时必须被拒绝
        with self.assertRaises(PermissionError) as ctx1:
            issue_benchmark_credential(
                model_id=self.model_name,
                volume_analytical_mm3=25000.0
            )
        self.assertIn("Unauthorized caller", str(ctx1.exception))

        # 8b: 提供错误 authority_key 时必须被拒绝
        with self.assertRaises(PermissionError) as ctx2:
            issue_benchmark_credential(
                model_id=self.model_name,
                volume_analytical_mm3=25000.0,
                authority_key="wrong_fake_key"
            )
        self.assertIn("Unauthorized caller", str(ctx2.exception))

        # 8c: 提供合法 authority_key 时签发成功
        cred = issue_benchmark_credential(
            model_id=self.model_name,
            volume_analytical_mm3=25000.0,
            authority_key="valid_authority_master_key_9999"
        )
        self.assertIsInstance(cred, BenchmarkCredential)


if __name__ == "__main__":
    unittest.main(verbosity=2)
