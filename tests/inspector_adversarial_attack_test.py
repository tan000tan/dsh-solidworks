"""
CAD 质量检查器对抗性攻击测试套件 (DEF-05 深度安全防伪验证)

测试目标：
验证攻击者仅修改普通输入字典，绝不能使不可信数据或克隆数据变成可信数据。
覆盖全部 14 种伪造攻击场景：
1. 浅拷贝伪造 (theo = dict(meas))
2. 深拷贝伪造 (theo = copy.deepcopy(meas))
3. 字典重构伪造 (theo = {k: v for k, v in meas.items()})
4. 伪造 provenance (theo["provenance"] = "independent_analytical")
5. 伪造 source (theo["source"] = "analytical")
6. 伪造/篡改模型 ID (跨模型复制凭证)
7. 伪造时间戳 (过期凭证 / 重放攻击)
8. 伪造测量结果 (篡改解析体积与载荷不符)
9. 重放旧凭证 (重放过期的历史凭证)
10. 跨模型复制凭证 (用其他模型的合法凭证套用在当前模型)
11. 缺失凭证 (普通无签名外部输入字典拒绝 VERIFIED)
12. 篡改凭证签名与 Nonce (密码学验签失败)
13. 相同多维数据直接克隆 (数值全等无独立代数推导)
14. 理论值和实测值来自同一份数据 (指针同一性 meas is theo)
以及合法基准对照：
15. 权威签发的合法凭证独立核验通过 (VERIFIED 且 is_acceptable=True)
"""
import copy
import os
import sys
import time
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "docs", "stage5_advanced_ai_cad", "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from cad_quality_inspector import (
    CadQualityInspector,
    BenchmarkCredential,
    issue_benchmark_credential,
    verify_benchmark_credential,
)


class TestInspectorAdversarialAttacks(unittest.TestCase):

    def setUp(self):
        self.inspector = CadQualityInspector()
        self.model_name = "stepped_shaft_production_01"
        self.measured_props = {
            "volume_mm3": 250743.571,  # 实测离散网格体积 (STL 积分值)
            "surface_area_mm2": 32150.4,
            "delta_x_mm": 50.0,
            "delta_y_mm": 50.0,
            "delta_z_mm": 180.0,
            "body_count": 1,
            "min_wall_thickness": 5.0,
        }
        self.analytical_volume = 251938.210  # 真实独立代数解析体积

    def test_01_shallow_copy_attack_intercepted(self):
        """攻击 1: 浅拷贝克隆攻击 (theo = dict(meas)) 必须被 FAILED 拦截且得 0 分"""
        forged_theo = dict(self.measured_props)
        self.assertIsNot(self.measured_props, forged_theo)

        report = self.inspector.inspect_quality(
            model_name=self.model_name,
            measured_props=self.measured_props,
            theoretical_props=forged_theo,
        )
        self.assertFalse(report.is_acceptable)
        self.assertEqual(report.verification_status, "FAILED")
        self.assertEqual(report.geometry_score.score, 0.0)
        self.assertTrue(report.metrics_summary.get("clone_attack_detected"))

    def test_02_deepcopy_attack_intercepted(self):
        """攻击 2: 深拷贝克隆攻击 (theo = copy.deepcopy(meas)) 必须被拦截"""
        forged_theo = copy.deepcopy(self.measured_props)
        report = self.inspector.inspect_quality(
            model_name=self.model_name,
            measured_props=self.measured_props,
            theoretical_props=forged_theo,
        )
        self.assertFalse(report.is_acceptable)
        self.assertEqual(report.verification_status, "FAILED")
        self.assertEqual(report.geometry_score.score, 0.0)

    def test_03_dict_reconstruction_attack_intercepted(self):
        """攻击 3: 字典重构攻击 (结构重建复制实测数据) 必须被拦截"""
        forged_theo = {k: v for k, v in self.measured_props.items()}
        report = self.inspector.inspect_quality(
            model_name=self.model_name,
            measured_props=self.measured_props,
            theoretical_props=forged_theo,
        )
        self.assertFalse(report.is_acceptable)
        self.assertEqual(report.verification_status, "FAILED")
        self.assertEqual(report.geometry_score.score, 0.0)

    def test_04_forged_provenance_bypass_intercepted(self):
        """攻击 4: 注入明文 provenance='independent_analytical' 绝对禁止豁免克隆检测"""
        forged_theo = dict(self.measured_props)
        forged_theo["provenance"] = "independent_analytical"

        report = self.inspector.inspect_quality(
            model_name=self.model_name,
            measured_props=self.measured_props,
            theoretical_props=forged_theo,
        )
        self.assertFalse(report.is_acceptable, "注入明文 provenance 绝不能逃逸克隆检测！")
        self.assertEqual(report.verification_status, "FAILED")
        self.assertEqual(report.geometry_score.score, 0.0)
        self.assertTrue(report.metrics_summary.get("clone_attack_detected"))

    def test_05_forged_source_bypass_intercepted(self):
        """攻击 5: 注入明文 source='analytical' 绝对禁止豁免克隆检测"""
        forged_theo = dict(self.measured_props)
        forged_theo["source"] = "analytical"

        report = self.inspector.inspect_quality(
            model_name=self.model_name,
            measured_props=self.measured_props,
            theoretical_props=forged_theo,
        )
        self.assertFalse(report.is_acceptable)
        self.assertEqual(report.verification_status, "FAILED")
        self.assertEqual(report.geometry_score.score, 0.0)

    def test_06_tampered_model_id_cross_model_intercepted(self):
        """攻击 6: 跨模型凭证盗用 (用合法模型 B 的凭证欺骗模型 A) 必须被阻断"""
        legit_cred_other_model = issue_benchmark_credential(
            model_id="other_bracket_model_99",
            volume_analytical_mm3=self.analytical_volume,
        )
        forged_theo = {
            "volume_mm3": self.analytical_volume,
            "credential": legit_cred_other_model,
        }
        report = self.inspector.inspect_quality(
            model_name=self.model_name,  # 传入当前模型名
            measured_props=self.measured_props,
            theoretical_props=forged_theo,
        )
        self.assertFalse(report.is_acceptable)
        self.assertEqual(report.verification_status, "FAILED")
        self.assertEqual(report.geometry_score.score, 0.0)
        self.assertTrue(report.metrics_summary.get("credential_forgery_detected"))

    def test_07_forged_expired_timestamp_replay_intercepted(self):
        """攻击 7: 伪造/重放已过期的历史凭证必须被阻断"""
        # 签发一个已经过期（TTL 为 -10 秒）的凭证
        expired_cred = issue_benchmark_credential(
            model_id=self.model_name,
            volume_analytical_mm3=self.analytical_volume,
            ttl_seconds=-10.0,
        )
        forged_theo = {
            "volume_mm3": self.analytical_volume,
            "credential": expired_cred,
        }
        report = self.inspector.inspect_quality(
            model_name=self.model_name,
            measured_props=self.measured_props,
            theoretical_props=forged_theo,
        )
        self.assertFalse(report.is_acceptable)
        self.assertEqual(report.verification_status, "FAILED")
        self.assertEqual(report.geometry_score.score, 0.0)

    def test_08_tampered_measurement_payload_hash_mismatch(self):
        """攻击 8: 篡改凭证内的理论测量数值而未重签名，触发载荷哈希不匹配"""
        cred = issue_benchmark_credential(
            model_id=self.model_name,
            volume_analytical_mm3=self.analytical_volume,
        )
        # 攻击者篡改数值
        tampered_cred_dict = cred.model_dump()
        tampered_cred_dict["volume_analytical_mm3"] = 999999.0

        forged_theo = {
            "volume_mm3": 999999.0,
            "credential": tampered_cred_dict,
        }
        report = self.inspector.inspect_quality(
            model_name=self.model_name,
            measured_props=self.measured_props,
            theoretical_props=forged_theo,
        )
        self.assertFalse(report.is_acceptable)
        self.assertEqual(report.verification_status, "FAILED")
        self.assertEqual(report.geometry_score.score, 0.0)

    def test_09_replay_old_credential_intercepted(self):
        """攻击 9: 截获并重放旧任务的历史凭据"""
        old_cred = issue_benchmark_credential(
            model_id=self.model_name,
            volume_analytical_mm3=self.analytical_volume,
            ttl_seconds=1.0,
        )
        time.sleep(1.05)  # 等待过期
        forged_theo = {
            "volume_mm3": self.analytical_volume,
            "credential": old_cred,
        }
        report = self.inspector.inspect_quality(
            model_name=self.model_name,
            measured_props=self.measured_props,
            theoretical_props=forged_theo,
        )
        self.assertFalse(report.is_acceptable)
        self.assertEqual(report.verification_status, "FAILED")

    def test_10_cross_model_copied_credential_intercepted(self):
        """攻击 10: 跨模型凭证混淆攻击"""
        cred_shaft = issue_benchmark_credential(
            model_id="remediated_stepped_shaft",
            volume_analytical_mm3=251938.21,
        )
        report = self.inspector.inspect_quality(
            model_name="remediated_gear",  # 在齿轮检查中复用轴的凭据
            measured_props=self.measured_props,
            theoretical_props={"credential": cred_shaft},
        )
        self.assertFalse(report.is_acceptable)
        self.assertEqual(report.verification_status, "FAILED")

    def test_11_missing_credential_unauthenticated_source(self):
        """攻击 11: 缺少密码学凭证的普通字典绝不允许获得 VERIFIED 满分"""
        plain_theo = {"volume_mm3": self.analytical_volume}  # 未提供 credential
        report = self.inspector.inspect_quality(
            model_name=self.model_name,
            measured_props=self.measured_props,
            theoretical_props=plain_theo,
        )
        self.assertFalse(report.is_acceptable, "未认证理论源绝不能获得 is_acceptable=True")
        self.assertEqual(report.verification_status, "NOT_VERIFIED")
        self.assertLessEqual(report.geometry_score.score, 60.0)

    def test_12_tampered_signature_intercepted(self):
        """攻击 12: 篡改凭证签名或伪造私钥签名"""
        cred = issue_benchmark_credential(
            model_id=self.model_name,
            volume_analytical_mm3=self.analytical_volume,
        )
        tampered_dict = cred.model_dump()
        tampered_dict["signature"] = "deadbeef" * 8  # 伪造签名
        report = self.inspector.inspect_quality(
            model_name=self.model_name,
            measured_props=self.measured_props,
            theoretical_props={"credential": tampered_dict},
        )
        self.assertFalse(report.is_acceptable)
        self.assertEqual(report.verification_status, "FAILED")

    def test_13_identical_numeric_data_direct_clone_intercepted(self):
        """攻击 13: 多个多维几何度量完全按位相同的直接克隆"""
        # 实测与理论虽然字典 key 不全同，但 volume、surface_area 完全一致
        identical_data = {
            "volume_mm3": self.measured_props["volume_mm3"],
            "surface_area_mm2": self.measured_props["surface_area_mm2"],
        }
        report = self.inspector.inspect_quality(
            model_name=self.model_name,
            measured_props=self.measured_props,
            theoretical_props=identical_data,
        )
        self.assertFalse(report.is_acceptable)
        self.assertEqual(report.verification_status, "FAILED")

    def test_14_pointer_identity_self_comparison_intercepted(self):
        """攻击 14: 指针完全同一性 (meas is theo)"""
        report = self.inspector.inspect_quality(
            model_name=self.model_name,
            measured_props=self.measured_props,
            theoretical_props=self.measured_props,
        )
        self.assertFalse(report.is_acceptable)
        self.assertEqual(report.verification_status, "FAILED")
        self.assertEqual(report.geometry_score.score, 0.0)

    def test_15_legitimate_verified_credential_success(self):
        """基准对照 15: 权威签发的合法凭证且数值具有真实工程微差，顺利 VERIFIED 通过"""
        # 阶梯轴实测 STL 离散网格体积为 250743.571，理论解析体积为 251938.210
        # 相对误差为 0.474%，在工程允许范围（< 1.0%）内，且持有权威签发凭据
        legit_cred = issue_benchmark_credential(
            model_id=self.model_name,
            volume_analytical_mm3=self.analytical_volume,
        )
        theo_payload = {
            "volume_mm3": self.analytical_volume,
            "credential": legit_cred,
        }
        report = self.inspector.inspect_quality(
            model_name=self.model_name,
            measured_props=self.measured_props,
            theoretical_props=theo_payload,
        )
        self.assertTrue(report.is_acceptable)
        self.assertEqual(report.verification_status, "VERIFIED")
        self.assertTrue(report.metrics_summary.get("credential_verified"))
        self.assertGreaterEqual(report.overall_quality_score, 80.0)


    def test_16_nonce_entropy_at_least_128_bit(self):
        """测试 16: Nonce 随机值熵至少 128 bit (16 字节 = 32 位十六进制)"""
        cred = issue_benchmark_credential(
            model_id=self.model_name,
            volume_analytical_mm3=self.analytical_volume,
        )
        parts = cred.nonce.split("_")
        self.assertGreaterEqual(len(parts), 3)
        random_hex = parts[-1]
        # 16 字节 = 32 位十六进制字符串 = 128 bit 熵
        self.assertGreaterEqual(len(random_hex), 32)
        int(random_hex, 16)  # 必须是合法的十六进制

    def test_17_concurrent_consumption_thread_safety(self):
        """测试 17: 多线程并发消费原子性与防竞争防御"""
        import threading
        cred = issue_benchmark_credential(
            model_id=self.model_name,
            volume_analytical_mm3=self.analytical_volume,
        )
        results = []

        def worker():
            ok, msg = verify_benchmark_credential(cred, model_id=self.model_name)
            results.append((ok, msg))

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        successes = [r for r in results if r[0] is True]
        failures = [r for r in results if r[0] is False]
        # 严格要求：恰好 1 次成功，其余 9 次全部被防重放拦截
        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 9)
        self.assertTrue(all("Replay attack intercepted" in r[1] for r in failures))

    def test_18_nonce_cache_capacity_and_expired_purge(self):
        """测试 18: Nonce 集合容量控制与过期清理防 DoS"""
        from cad_quality_inspector import _CONSUMED_NONCES, _purge_expired_nonces, clear_consumed_nonces
        clear_consumed_nonces()
        now = time.time()
        # 插入过期 Nonce
        _CONSUMED_NONCES["expired_1"] = now - 100
        _CONSUMED_NONCES["expired_2"] = now - 50
        _CONSUMED_NONCES["active_1"] = now + 1000

        _purge_expired_nonces(now)
        self.assertNotIn("expired_1", _CONSUMED_NONCES)
        self.assertNotIn("expired_2", _CONSUMED_NONCES)
        self.assertIn("active_1", _CONSUMED_NONCES)
        clear_consumed_nonces()

    def test_19_secret_rotation_invalidation(self):
        """测试 19: 秘钥动态轮换后旧会话凭据失效隔离"""
        from cad_quality_inspector import rotate_benchmark_secret, get_benchmark_secret
        old_secret = get_benchmark_secret()
        cred = issue_benchmark_credential(
            model_id=self.model_name,
            volume_analytical_mm3=self.analytical_volume,
            secret_key=old_secret,
        )
        # 轮换秘钥
        new_secret = rotate_benchmark_secret()
        self.assertNotEqual(old_secret, new_secret)

        # 用新秘钥核验旧凭证，签名必须失效
        ok, msg = verify_benchmark_credential(cred, model_id=self.model_name, secret_key=new_secret)
        self.assertFalse(ok)
        self.assertIn("forged signature", msg)

        # 换回原秘钥复原状态
        rotate_benchmark_secret(old_secret)

if __name__ == "__main__":
    unittest.main()
