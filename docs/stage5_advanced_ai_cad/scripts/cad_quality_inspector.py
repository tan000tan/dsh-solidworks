"""

多维综合质量评价与优化引擎 (CAD Quality Inspector - Remediated Version)

对应第五阶段子阶段 S5-E 整改版：

整改要点：

1. 统一键名与单位：兼容 volume 与 volume_mm3，surface_area 与 surface_area_mm2，严格校验数据合法性。

2. 自比对探测与防御：严格检查实测值与理论值是否为同一内存对象或同一来源且未显式声明，拦截虚假自比对。

3. 理论值缺失严格处理：当缺少理论解析体积时，明确标记为 NOT VERIFIED，不给予虚假满分，几何项封顶并标记不合格。

4. 异常数值防御：处理负值、零值、NaN、非数字类型等非法输入。

5. 详细记录实测值、理论值、允许公差、实际绝对误差、相对误差与判定状态。

"""

import math

import os

import hashlib

import hmac

import time

import copy

import threading

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field



import secrets



# 动态权威私钥：优先从环境变量加载，未显式注入时生成高熵安全临时会话私钥，彻底移除明文硬编码

_ENV_BENCHMARK_SECRET = "CAD_BENCHMARK_SECRET"

_DYNAMIC_SESSION_SECRET = None



def get_benchmark_secret() -> str:

    """动态获取基准凭据签名私钥，严禁代码硬编码静态私钥"""

    env_key = os.environ.get(_ENV_BENCHMARK_SECRET)

    if env_key and len(env_key.strip()) >= 16:

        return env_key.strip()

    global _DYNAMIC_SESSION_SECRET

    if _DYNAMIC_SESSION_SECRET is None:

        _DYNAMIC_SESSION_SECRET = secrets.token_hex(32)

    return _DYNAMIC_SESSION_SECRET



def rotate_benchmark_secret(new_secret: Optional[str] = None) -> str:

    """支持在运行时安全动态轮换基准签名私钥"""

    global _DYNAMIC_SESSION_SECRET, BENCHMARK_SECRET

    _DYNAMIC_SESSION_SECRET = new_secret or secrets.token_hex(32)

    BENCHMARK_SECRET = _DYNAMIC_SESSION_SECRET

    return _DYNAMIC_SESSION_SECRET



# 保持属性兼容性（动态委托）
BENCHMARK_SECRET = get_benchmark_secret()

# 线程安全与跨进程安全的 Nonce 消费池与容量上限控制（防 DoS 内存溢出）
MAX_CONSUMED_NONCES = 10000
_NONCE_LOCK = threading.Lock()
_CONSUMED_NONCES: Dict[str, float] = {}  # mapping: nonce -> expires_at

import json
import tempfile
from contextlib import contextmanager

try:
    import msvcrt
except ImportError:
    msvcrt = None

try:
    import fcntl
except ImportError:
    fcntl = None

_ENV_NONCE_STORE = "CAD_NONCE_STORE_PATH"
_ENV_REQUIRE_AUTHORITY_KEY = "CAD_REQUIRE_AUTHORITY_KEY"
_ENV_AUTHORITY_KEY = "CAD_AUTHORITY_KEY"

def _get_nonce_store_path() -> str:
    path = os.environ.get(_ENV_NONCE_STORE)
    if not path:
        path = os.path.join(tempfile.gettempdir(), ".dsh_cad_consumed_nonces.json")
    return os.path.abspath(path)

@contextmanager
def _interprocess_file_lock(lock_file_path: str):
    """跨进程文件锁上下文管理器（支持 Windows 与 POSIX）"""
    lock_path = lock_file_path + ".lock"
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    lock_file = open(lock_path, "a+b")
    acquired = False
    try:
        if msvcrt is not None:
            for _ in range(50):
                try:
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                    acquired = True
                    break
                except (BlockingIOError, OSError):
                    time.sleep(0.05)
            if not acquired:
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
                acquired = True
        elif fcntl is not None:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            acquired = True
        else:
            acquired = True
        yield
    finally:
        if acquired:
            try:
                if msvcrt is not None:
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                elif fcntl is not None:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
        try:
            lock_file.close()
        except Exception:
            pass

def _load_persisted_nonces(file_path: str) -> Dict[str, float]:
    """从持久化文件安全加载已消费 Nonce"""
    if not os.path.exists(file_path):
        return {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return {str(k): float(v) for k, v in data.items() if isinstance(v, (int, float))}
    except Exception:
        pass
    return {}

def _save_persisted_nonces(file_path: str, nonces: Dict[str, float]) -> None:
    """原子持久化写入已消费 Nonce"""
    dir_name = os.path.dirname(file_path)
    os.makedirs(dir_name, exist_ok=True)
    tmp_path = file_path + f".tmp.{os.getpid()}.{time.time_ns()}"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(nonces, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, file_path)
    except Exception:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        raise

def _purge_expired_nonces(now: float) -> None:
    """清理已过期的 Nonce 记录。严格遵循 Fail-Closed 原则：绝不驱逐未过期的 Nonce。"""
    expired_keys = [k for k, exp in _CONSUMED_NONCES.items() if exp < now]
    for k in expired_keys:
        del _CONSUMED_NONCES[k]

def clear_consumed_nonces():
    """测试重置辅助函数：清空内存与跨进程持久化存储"""
    store_path = _get_nonce_store_path()
    with _NONCE_LOCK:
        _CONSUMED_NONCES.clear()
        try:
            with _interprocess_file_lock(store_path):
                if os.path.exists(store_path):
                    try:
                        os.remove(store_path)
                    except Exception:
                        pass
        except Exception:
            pass


class BenchmarkCredential(BaseModel):
    """权威基准签发机构密码学凭据 (防重放、防跨模型、防内容篡改)"""
    issuer: str = "cad_benchmark_authority"
    model_id: str
    issued_at: float
    expires_at: float
    nonce: str
    volume_analytical_mm3: float
    payload_hash: str
    signature: str


def issue_benchmark_credential(
    model_id: str,
    volume_analytical_mm3: float,
    secret_key: Optional[str] = None,
    ttl_seconds: float = 3600.0,
    nonce: Optional[str] = None,
    authority_key: Optional[str] = None
) -> BenchmarkCredential:
    """签发权威独立的几何基准凭据"""
    # 权威签发权限校验 (Authority Boundary Guard)
    req_authority = os.environ.get(_ENV_REQUIRE_AUTHORITY_KEY, "").strip().lower() in ("1", "true", "yes")
    if req_authority:
        expected_authority = os.environ.get(_ENV_AUTHORITY_KEY, "")
        if not expected_authority or not authority_key or not hmac.compare_digest(str(authority_key), str(expected_authority)):
            raise PermissionError("Unauthorized caller cannot issue benchmark credentials: valid authority key required")

    actual_secret = secret_key or get_benchmark_secret()
    now = time.time()
    n = nonce or f"nonce_{int(now*1000)}_{secrets.token_hex(16)}"
    exp = now + ttl_seconds
    payload_str = f"{model_id}:{volume_analytical_mm3:.6f}:{now:.3f}:{exp:.3f}:{n}"
    p_hash = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()
    sig = hmac.new(actual_secret.encode("utf-8"), p_hash.encode("utf-8"), hashlib.sha256).hexdigest()
    return BenchmarkCredential(
        issuer="cad_benchmark_authority",
        model_id=model_id,
        issued_at=now,
        expires_at=exp,
        nonce=n,
        volume_analytical_mm3=volume_analytical_mm3,
        payload_hash=p_hash,
        signature=sig
    )


def verify_benchmark_credential(
    cred: BenchmarkCredential,
    model_id: str,
    secret_key: Optional[str] = None,
    current_time: Optional[float] = None
) -> tuple[bool, str]:
    """密码学核验基准凭据的有效性与上下文绑定"""
    if not isinstance(cred, BenchmarkCredential):
        return False, "Invalid credential type"
    now = current_time if current_time is not None else time.time()
    if now > cred.expires_at:
        return False, f"Credential expired at {cred.expires_at}, current time is {now} (replay attack intercepted)"
    if cred.model_id != model_id:
        return False, f"Model ID mismatch: credential bound to '{cred.model_id}', but inspected model is '{model_id}' (cross-model copy attack intercepted)"
    
    # 重算载荷哈希
    payload_str = f"{cred.model_id}:{cred.volume_analytical_mm3:.6f}:{cred.issued_at:.3f}:{cred.expires_at:.3f}:{cred.nonce}"
    computed_hash = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()
    if not hmac.compare_digest(computed_hash, cred.payload_hash):
        return False, "Payload hash mismatch: credential content was tampered"
        
    # 验证 HMAC 签名：动态获取最新私钥，彻底修复默认参数在模块加载期固化的竞态缺陷
    actual_secret = secret_key if secret_key is not None else get_benchmark_secret()
    expected_sig = hmac.new(actual_secret.encode("utf-8"), cred.payload_hash.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_sig, cred.signature):
        return False, "Cryptographic signature invalid: forged signature"

    # 防重放校验：原子消费内存与持久化存储中的 Nonce
    store_path = _get_nonce_store_path()
    with _NONCE_LOCK:
        with _interprocess_file_lock(store_path):
            persisted = _load_persisted_nonces(store_path)
            _CONSUMED_NONCES.update(persisted)
            _purge_expired_nonces(now)
            if cred.nonce in _CONSUMED_NONCES:
                return False, f"Replay attack intercepted: nonce '{cred.nonce}' was already used"
            if len(_CONSUMED_NONCES) >= MAX_CONSUMED_NONCES:
                return False, (
                    "Security restriction: Nonce verification capacity reached maximum limit. "
                    "New verifications rejected to prevent replay attacks (fail-closed)."
                )
            _CONSUMED_NONCES[cred.nonce] = cred.expires_at
            _save_persisted_nonces(store_path, _CONSUMED_NONCES)

    return True, "OK"







class QualityCategoryScore(BaseModel):

    """单个维度的质量评价分项"""

    category_name: str

    score: float                    # 0.0 ~ 100.0

    weight: float                   # 权重 (例如 0.3)

    status: str = "VERIFIED"        # VERIFIED, PARTIALLY_VERIFIED, NOT_VERIFIED, FAILED

    passed_checks: List[str] = Field(default_factory=list)

    failed_checks: List[str] = Field(default_factory=list)

    warnings: List[str] = Field(default_factory=list)





class ComprehensiveQualityReport(BaseModel):

    """多维综合质量评估最终报告"""

    model_name: str

    overall_quality_score: float    # 综合总分 (0.0 ~ 100.0)

    is_acceptable: bool             # 总分 >= 80 且无致命项

    verification_status: str        # VERIFIED, PARTIAL, NOT_VERIFIED, FAILED

    geometry_score: QualityCategoryScore

    topology_score: QualityCategoryScore

    stability_score: QualityCategoryScore

    manufacturing_score: QualityCategoryScore

    metrics_summary: Dict[str, Any] = Field(default_factory=dict)

    actionable_recommendations: List[str] = Field(default_factory=list)





def _extract_number(data: Dict[str, Any], *keys, default=None) -> Optional[float]:

    """安全提取指定键名候选列表中的浮点数值"""

    if not isinstance(data, dict):

        return default

    for k in keys:

        if k in data and data[k] is not None:

            try:

                v = float(data[k])

                if math.isnan(v) or math.isinf(v):

                    return None

                return v

            except (ValueError, TypeError):

                return None

    return default





class CadQualityInspector:

    """多维 CAD 质量检查器 (修复与防御增强版)"""



    def __init__(self):

        # 四个维度的基准权重：几何 30%，拓扑 25%，稳定性 25%，工艺性 20%

        self.weights = {

            "geometry": 0.30,

            "topology": 0.25,

            "stability": 0.25,

            "manufacturing": 0.20

        }



    def inspect_quality(

        self,

        model_name: str,

        measured_props: Dict[str, Any],

        theoretical_props: Optional[Dict[str, Any]] = None,

        feature_point_samples: Optional[Dict[str, List[float]]] = None,

        expected_point_samples: Optional[Dict[str, List[float]]] = None,

        rebuild_time_sec: float = 0.5,

        sketch_constrained_status: str = "FULLY_CONSTRAINED",

        independent_theoretical_source: bool = True

    ) -> ComprehensiveQualityReport:

        """

        执行综合多维质量评价

        """

        # 1. 几何维度核验 (含宏观体积、自比对防范与局部微观坐标采样)

        geom_cat, geom_metrics = self._evaluate_geometry(

            measured_props, theoretical_props, feature_point_samples, expected_point_samples,

            independent_theoretical_source=independent_theoretical_source,

            model_name=model_name

        )



        # 2. 拓扑与约束规范核验

        topo_cat = self._evaluate_topology(sketch_constrained_status, measured_props)



        # 3. 重建稳定性核验

        stab_cat = self._evaluate_stability(rebuild_time_sec)



        # 4. 机械加工工艺性核验

        mfg_cat = self._evaluate_manufacturing(measured_props)



        # 5. 计算加权总分

        overall = (

            geom_cat.score * self.weights["geometry"] +

            topo_cat.score * self.weights["topology"] +

            stab_cat.score * self.weights["stability"] +

            mfg_cat.score * self.weights["manufacturing"]

        )

        overall = max(0.0, min(100.0, overall))



        # 6. 收集优化建议

        recommendations = []

        for cat in [geom_cat, topo_cat, stab_cat, mfg_cat]:

            for w in cat.warnings:

                recommendations.append(f"[{cat.category_name} 优化项] {w}")

            for f in cat.failed_checks:

                recommendations.append(f"[{cat.category_name} 整改项] {f}")



        # 判定最终接受状态：总分 >= 80，几何项必须为 VERIFIED，且各维度不得有任何 FAILED 或未通过检查项

        all_categories = [geom_cat, topo_cat, stab_cat, mfg_cat]

        has_any_failed = any(c.status == "FAILED" or len(c.failed_checks) > 0 for c in all_categories)

        is_acc = (overall >= 80.0) and (not has_any_failed) and (geom_cat.status == "VERIFIED")



        verdict_status = "VERIFIED"

        if not is_acc:

            if has_any_failed or len(geom_cat.failed_checks) > 0:

                verdict_status = "FAILED"

            elif geom_cat.status == "NOT_VERIFIED":

                verdict_status = "NOT_VERIFIED"

            else:

                verdict_status = "PARTIALLY_VERIFIED"



        return ComprehensiveQualityReport(

            model_name=model_name,

            overall_quality_score=round(overall, 1),

            is_acceptable=is_acc,

            verification_status=verdict_status,

            geometry_score=geom_cat,

            topology_score=topo_cat,

            stability_score=stab_cat,

            manufacturing_score=mfg_cat,

            metrics_summary=geom_metrics,

            actionable_recommendations=recommendations

        )



    def _evaluate_geometry(

        self,

        measured: Dict[str, Any],

        theoretical: Optional[Dict[str, Any]],

        samples: Optional[Dict[str, List[float]]],

        expected_samples: Optional[Dict[str, List[float]]],

        independent_theoretical_source: bool = True,

        model_name: str = "UnknownPart"

    ) -> tuple[QualityCategoryScore, Dict[str, Any]]:

        score = 100.0

        passed = []

        failed = []

        warnings = []

        status = "VERIFIED"

        metrics: Dict[str, Any] = {}



        # 提取实测体积与理论体积 (兼容 volume 与 volume_mm3)

        v_meas = _extract_number(measured, "volume", "volume_mm3")

        v_theo = _extract_number(theoretical, "volume", "volume_mm3") if theoretical else None



        # (0) 彻底防御克隆、伪造与未授权自比对 (DEF-05 重构防伪引擎)

        cred_obj: Optional[BenchmarkCredential] = None

        has_verified_credential = False



        if theoretical is not None:

            # 1. 指针同一性检查

            if measured is theoretical:

                failed.append("严重安全拦截：实测值与理论值指向完全相同的字典对象 (自比对虚假核验)")

                score = 0.0

                status = "FAILED"

                metrics["self_comparison_detected"] = True

                return QualityCategoryScore(

                    category_name="几何尺寸与局部微观坐标",

                    score=0.0,

                    weight=self.weights["geometry"],

                    status="FAILED",

                    passed_checks=passed,

                    failed_checks=failed,

                    warnings=warnings

                ), metrics



            # 2. 彻底废除调用方明文 provenance/source 免检逻辑

            # 普通字典中的 provenance 或 source 字段绝不赋予绕过克隆检测的特权！

            if isinstance(theoretical, dict) and any(k in theoretical for k in ("provenance", "source")):

                warnings.append("安全提示：普通字典明文字符串 provenance/source 无法作为信任凭据，已被安全降级")

                metrics["plaintext_provenance_rejected"] = True



            # 3. 密码学基准凭证校验 (如果提供了 credential)

            if isinstance(theoretical, dict) and "credential" in theoretical:

                raw_cred = theoretical["credential"]

                if isinstance(raw_cred, BenchmarkCredential):

                    cred_obj = raw_cred

                elif isinstance(raw_cred, dict):

                    try:

                        cred_obj = BenchmarkCredential(**raw_cred)

                    except Exception as exc:

                        failed.append(f"安全拦截：基准凭证字段缺失或反序列化失败 ({exc})")

                        score = 0.0

                        status = "FAILED"

                        metrics["credential_forgery_detected"] = True

                        return QualityCategoryScore(

                            category_name="几何尺寸与局部微观坐标",

                            score=0.0,

                            weight=self.weights["geometry"],

                            status="FAILED",

                            passed_checks=passed,

                            failed_checks=failed,

                            warnings=warnings

                        ), metrics



            if cred_obj is not None:

                is_valid, cred_reason = verify_benchmark_credential(cred_obj, model_name)

                if not is_valid:

                    failed.append(f"安全拦截：基准凭证核验失败 ({cred_reason})，拒绝采信伪造理论源")

                    score = 0.0

                    status = "FAILED"

                    metrics["credential_forgery_detected"] = True

                    return QualityCategoryScore(

                        category_name="几何尺寸与局部微观坐标",

                        score=0.0,

                        weight=self.weights["geometry"],

                        status="FAILED",

                        passed_checks=passed,

                        failed_checks=failed,

                        warnings=warnings

                    ), metrics

                else:

                    passed.append(f"基准凭证经由 [{cred_obj.issuer}] 密码学验签通过 (model_id={cred_obj.model_id})")

                    metrics["credential_verified"] = True

                    has_verified_credential = True

                    # 权威理论体积采用凭证内受保护的数据

                    v_theo = cred_obj.volume_analytical_mm3



            # 4. 字典浅拷贝、深拷贝、结构重构与克隆检测

            ignored_keys = {"provenance", "source", "credential", "token", "signature", "nonce", "issuer"}

            meas_core = {k: v for k, v in measured.items() if not k.startswith("_") and k not in ignored_keys} if isinstance(measured, dict) else {}

            theo_core = {k: v for k, v in theoretical.items() if not k.startswith("_") and k not in ignored_keys} if isinstance(theoretical, dict) else {}



            is_clone = False

            if meas_core and theo_core and not has_verified_credential:

                # 浅拷贝、深拷贝或字典完全重构

                if meas_core == theo_core:

                    is_clone = True

                else:

                    # 检查共享数值字段：若所有共享数值完全按位相同且包含 volume

                    shared_numeric = {k: meas_core[k] for k in meas_core if k in theo_core and isinstance(meas_core[k], (int, float))}

                    if len(shared_numeric) >= 1 and all(meas_core[k] == theo_core[k] for k in shared_numeric):

                        if not has_verified_credential and len(meas_core) > 1 and len(theo_core) > 1:

                            is_clone = True



            if is_clone:

                failed.append("严重安全拦截：理论值系实测数据直接克隆/篡改 (dict/deepcopy clone bypass detected)，未通过独立解析源验证")

                score = 0.0

                status = "FAILED"

                metrics["clone_attack_detected"] = True

                return QualityCategoryScore(

                    category_name="几何尺寸与局部微观坐标",

                    score=0.0,

                    weight=self.weights["geometry"],

                    status="FAILED",

                    passed_checks=passed,

                    failed_checks=failed,

                    warnings=warnings

                ), metrics



            # 5. 普通未签名外部理论源：无法证实独立性时绝不给满分，标记 NOT_VERIFIED

            if not has_verified_credential:

                if not independent_theoretical_source:

                    warnings.append("安全提示：理论数据源未提供密码学基准凭证或独立代数推导过程证明，存在偶合风险")

                    score -= 40.0

                    status = "NOT_VERIFIED"

                else:

                    # 即便标记 independent_theoretical_source=True，若无凭据，仍需降级提示

                    warnings.append("理论数据源为普通未签名输入，缺少独立签发凭据")

                    score = min(score, 60.0)

                    status = "NOT_VERIFIED"



        # (1) 宏观体积核验

        if v_meas is None or v_meas <= 0:

            failed.append(f"实测体积非法或非正数 (实测值={v_meas})")

            score = 0.0

            status = "FAILED"

        elif v_theo is None:

            # 严格整改：没有理论值不得报告 100 分，明确标记 NOT_VERIFIED！

            warnings.append("缺少理论解析体积，无法执行独立相对误差计算")

            score -= 40.0 # 缺少理论值扣除几何项 40 分

            status = "NOT_VERIFIED"

            passed.append(f"实测体积有效且大于零 ({v_meas:.2f} mm³)")

            metrics["volume_measured_mm3"] = v_meas

            metrics["volume_theoretical_mm3"] = None

            metrics["volume_relative_error"] = None

        elif v_theo <= 0:

            failed.append(f"理论解析体积定义非法或非正数 (理论值={v_theo})")

            score -= 50.0

            status = "FAILED"

        else:

            # 正常执行独立比对

            err_v = abs(v_meas - v_theo) / v_theo

            metrics["volume_measured_mm3"] = v_meas

            metrics["volume_theoretical_mm3"] = v_theo

            metrics["volume_relative_error"] = err_v



            # 探测数值完全雷同但无理论推导的自填充

            if err_v == 0.0 and (v_meas > 1000.0) and (not isinstance(v_theo, int)) and (len(str(v_meas)) == len(str(v_theo))):

                if samples == expected_samples and samples is not None:

                    warnings.append("警告：实测值与理论值浮点完全重合且采样点完全一致，请确认非复制填充")



            if err_v <= 0.0005:  # 0.05% 以内

                passed.append(f"宏观体积误差吻合优秀 (实测={v_meas:.2f}, 理论={v_theo:.2f}, 相对误差={err_v*100:.4f}% <= 0.05%)")

            elif err_v <= 0.01:   # 1.0% 以内

                score -= 10.0

                warnings.append(f"宏观体积相对误差偏大 (相对误差={err_v*100:.2f}%)")

            else:

                score -= 40.0

                failed.append(f"宏观体积超标严重 (实测={v_meas:.2f}, 理论={v_theo:.2f}, 相对误差={err_v*100:.2f}% > 1.0%)")

                status = "FAILED"



        # (2) 微观坐标采样核验

        if samples and expected_samples:

            max_dev = 0.0

            for pt_name, pt_meas in samples.items():

                if pt_name in expected_samples:

                    pt_exp = expected_samples[pt_name]

                    dist = math.sqrt(sum((a - b)**2 for a, b in zip(pt_meas, pt_exp)))

                    max_dev = max(max_dev, dist)

                    if dist > 0.005:  # 超出 5 微米公差

                        score -= 35.0

                        failed.append(

                            f"关键特征采样点 [{pt_name}] 坐标偏移超差: 实测 {pt_meas}, 预期 {pt_exp}, 偏差 {dist:.4f}mm > 0.005mm"

                        )

                        status = "FAILED"

                    else:

                        passed.append(f"关键特征点 [{pt_name}] 空间坐标精准吻合 (偏差={dist*1000:.1f}um)")

            metrics["max_point_deviation_mm"] = max_dev

        elif expected_samples and not samples:

            warnings.append("缺少实测微观空间采样点，微观几何项未覆盖")

            score -= 15.0



        return QualityCategoryScore(

            category_name="几何尺寸与局部微观坐标",

            score=max(0.0, score),

            weight=self.weights["geometry"],

            status=status,

            passed_checks=passed,

            failed_checks=failed,

            warnings=warnings

        ), metrics



    def _evaluate_topology(

        self,

        sketch_status: str,

        measured: Dict[str, Any]

    ) -> QualityCategoryScore:

        score = 100.0

        passed = []

        failed = []

        warnings = []

        status = "VERIFIED"



        if sketch_status == "FULLY_CONSTRAINED":

            passed.append("草图几何约束处于完全定义 (Fully Defined) 稳定状态")

        elif sketch_status == "UNDER_CONSTRAINED":

            score -= 30.0

            warnings.append("草图存在欠定义 (Under-defined) 元素，后续参数修改容易引发漂移")

            status = "PARTIALLY_VERIFIED"

        elif sketch_status == "OVER_CONSTRAINED":

            score -= 40.0

            failed.append("草图存在过定义 (Over-defined) 冲突约束")

            status = "FAILED"



        body_count = measured.get("body_count", 1)

        if body_count == 1:

            passed.append("单实体零件拓扑闭合完整")

        else:

            warnings.append(f"零件包含 {body_count} 个独立非合并实体，需确认是否为设计意图")



        return QualityCategoryScore(

            category_name="拓扑规范与草图约束",

            score=max(0.0, score),

            weight=self.weights["topology"],

            status=status,

            passed_checks=passed,

            failed_checks=failed,

            warnings=warnings

        )



    def _evaluate_stability(self, rebuild_time_sec: float) -> QualityCategoryScore:

        score = 100.0

        passed = []

        failed = []

        warnings = []

        status = "VERIFIED"



        if rebuild_time_sec <= 1.0:

            passed.append(f"模型强制重建响应迅速 ({rebuild_time_sec:.2f}s <= 1.0s)")

        elif rebuild_time_sec <= 3.0:

            score -= 10.0

            warnings.append(f"模型重建耗时偏长 ({rebuild_time_sec:.2f}s)")

            status = "PARTIALLY_VERIFIED"

        else:

            score -= 30.0

            failed.append(f"模型特征计算负荷沉重，重建严重滞后 ({rebuild_time_sec:.2f}s > 3.0s)")

            status = "FAILED"



        return QualityCategoryScore(

            category_name="重建稳定性与计算负荷",

            score=max(0.0, score),

            weight=self.weights["stability"],

            status=status,

            passed_checks=passed,

            failed_checks=failed,

            warnings=warnings

        )



    def _evaluate_manufacturing(self, measured: Dict[str, Any]) -> QualityCategoryScore:

        score = 100.0

        passed = []

        failed = []

        warnings = []

        status = "VERIFIED"



        min_wall = _extract_number(measured, "min_wall_thickness", default=5.0)

        if min_wall is not None and min_wall < 1.5:

            score -= 25.0

            warnings.append(f"检测到薄壁结构 (最小壁厚 {min_wall:.2f}mm < 1.5mm)，加工时存在振刀与变形风险")

            status = "PARTIALLY_VERIFIED"

        else:

            passed.append(f"壁厚满足常规切削加工要求 ({min_wall:.2f}mm >= 1.5mm)")



        has_sharp_internal_corners = measured.get("has_sharp_internal_corners", False)

        if has_sharp_internal_corners:

            score -= 20.0

            warnings.append("存在内凹尖角未执行倒圆角 (应力集中源，建议增加 R2~R3 圆角)")

        else:

            passed.append("内角平滑过渡良好")



        return QualityCategoryScore(

            category_name="机械加工工艺性",

            score=max(0.0, score),

            weight=self.weights["manufacturing"],

            status=status,

            passed_checks=passed,

            failed_checks=failed,

            warnings=warnings

        )

