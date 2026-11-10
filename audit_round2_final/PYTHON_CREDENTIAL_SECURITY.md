# Python 质量凭据安全机制、架构风险与持久化防重放整改报告

**审查对象**: `docs/stage5_advanced_ai_cad/scripts/cad_quality_inspector.py` 中的 `BenchmarkCredential` 密码学凭据体系  
**测试脚本**: `tests/python_credential_security_test.py`  
**验证状态**: **8/8 反向测试完全通过 (PASS)**

---

## 一、基准凭据机制架构剖析

在 CAD 自动化与 AI 建模质量核验中，系统引入了权威独立的几何基准凭据 `BenchmarkCredential`，以彻底根除“自比对虚假核验”和“虚假满分”漏洞。

### 1. 凭据核心数据模型
```python
class BenchmarkCredential(BaseModel):
    issuer: str = "cad_benchmark_authority"
    model_id: str                      # 绑定的模型标识 (防跨模型复用)
    issued_at: float                   # 签发时间戳
    expires_at: float                  # 到期时间戳 (默认 TTL 3600s)
    nonce: str                         # 高熵随机数 (单次消费防重放)
    volume_analytical_mm3: float       # 权威解析几何体积
    payload_hash: str                  # SHA-256(model_id:vol:issued:exp:nonce)
    signature: str                     # HMAC-SHA256(secret, payload_hash)
```

### 2. 私钥来源与生命周期
- **动态密钥机制**: 优先从环境变量 `CAD_BENCHMARK_SECRET` 读取。若未配置，则在模块加载时通过 `secrets.token_hex(32)` 生成高熵临时会话密钥，彻底移除了代码中硬编码的静态密钥。
- **密钥轮换支持**: 提供 `rotate_benchmark_secret()` 函数，支持在运行时安全动态轮换。

---

## 二、上轮审查揭示的深层风险剖析

在第二轮独立审查中，独立审计者指出了原有凭据体系的 3 大关键弱点：
1. **纯内存 Nonce 池漏洞**: 原先已消费 Nonce 保存在进程内存中的 `_CONSUMED_NONCES: Dict[str, float]` 字典内。一旦进程退出重启，或由独立子进程并行调用核验时，新进程对历史消费的 Nonce 完全不可见，攻击者可在凭据有效期（TTL）内发起**跨进程或跨重启的重放攻击**。
2. **签发权威边界缺失**: 任何能导入该模块的代码均可直接调用 `issue_benchmark_credential` 自行签发带有合法签名的凭据，缺少权威调用方身份校验。
3. **缺乏系统性反向用例**: 缺少对篡改、过期、重放等边界条件的自动化安全测试套件。

---

## 三、本轮架构增强与整改实现

针对上述缺陷，我们在本轮进行了源码级重构与加固：

### 1. 跨进程互斥文件锁与持久化存储
在 [`cad_quality_inspector.py`](file:///D:/Agent工作区/DeepSeek%20Harness工作区/dsh-solidworks-plugin/docs/stage5_advanced_ai_cad/scripts/cad_quality_inspector.py) 中：
- **存储路径**: 通过环境变量 `CAD_NONCE_STORE_PATH` 可配置，默认指向临时目录安全文件 `.dsh_cad_consumed_nonces.json`。
- **跨平台互斥锁 (`_interprocess_file_lock`)**:
  - Windows 环境: 采用 `msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK / LK_LOCK, 1)` 进行字节级非阻塞重试与阻塞获取；
  - POSIX 环境: 采用 `fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)`；
- **原子持久化 (`_save_persisted_nonces`)**: 采用“写临时文件 + `os.fsync` + `os.replace`”策略，确保即便进程意外崩溃也不会损坏 Nonce 数据库文件。

### 2. 严格 Fail-Closed 防御原则
- 当总 Nonce 数量达到 `MAX_CONSUMED_NONCES` (10,000 条) 且不可驱逐时，系统**拒绝**新的凭据核验，坚决防止内存或磁盘 DoS 耗尽。
- 绝不提前驱逐任何未到期的 Nonce。

### 3. 权威边界鉴权防护 (Authority Boundary Guard)
在 `issue_benchmark_credential` 中增加权限校验逻辑：
```python
req_authority = os.environ.get("CAD_REQUIRE_AUTHORITY_KEY", "").strip().lower() in ("1", "true", "yes")
if req_authority:
    expected_authority = os.environ.get("CAD_AUTHORITY_KEY", "")
    if not expected_authority or not authority_key or not hmac.compare_digest(str(authority_key), str(expected_authority)):
        raise PermissionError("Unauthorized caller cannot issue benchmark credentials: valid authority key required")
```

---

## 四、8 项反向安全测试执行结果与证据

编写了专项反向测试套件 [`tests/python_credential_security_test.py`](file:///D:/Agent工作区/DeepSeek%20Harness工作区/dsh-solidworks-plugin/tests/python_credential_security_test.py)，执行命令与原始日志保存在 `audit_round2_final/RAW_TEST_LOGS/python_credential_security.log`。

| 测试序号 | 测试用例名称 | 模拟攻击场景与验证逻辑 | 预期行为与安全断言 | 实际执行结果 |
| :--- | :--- | :--- | :--- | :--- |
| **TEST-01** | `test_01_no_credential` | 理论输入中未包含密码学凭证（仅普通数值） | 防御自比对机制生效，几何核验严格降级为 `NOT_VERIFIED`，不得获得权威背书 | **PASS** (耗时 0.05s) |
| **TEST-02** | `test_02_invalid_credential` | 传入缺失 `signature`/`hash` 或结构破坏的凭据 | 触发反序列化拦截，几何项判为 0 分，状态为 `FAILED`，记录 `credential_forgery_detected` | **PASS** (耗时 0.04s) |
| **TEST-03** | `test_03_expired_credential` | 传入 `expires_at < current_time` 的已过期凭据 | 校验器返回 `Credential expired (replay attack intercepted)`，判定为 `FAILED` | **PASS** (耗时 0.05s) |
| **TEST-04** | `test_04_tampered_credential` | 篡改 `volume_analytical_mm3` 或跨模型冒用 | 载荷哈希计算不一致，返回 `Payload hash mismatch: credential content was tampered` | **PASS** (耗时 0.05s) |
| **TEST-05** | `test_05_replayed_nonce_same_process` | 同一进程内使用相同 Nonce 连续发起两次验证 | 第一次验证通过，第二次命中内存 Nonce 记录，返回 `Replay attack intercepted` | **PASS** (耗时 0.04s) |
| **TEST-06** | `test_06_replayed_nonce_across_restart` | 第一次消费后，清空内存 `_CONSUMED_NONCES`（模拟重启），再次验证 | 持久化层通过文件读取历史记录，成功阻断重放，返回 `Replay attack intercepted` | **PASS** (耗时 0.05s) |
| **TEST-07** | `test_07_replayed_nonce_across_separate_processes` | 启动子进程 P1 消费 Nonce，再启动独立子进程 P2 尝试消费相同 Nonce | 进程 P1 退出码 0，进程 P2 被持久化存储拦截并返回退出码 2，彻底阻断跨进程重放 | **PASS** (耗时 0.08s) |
| **TEST-08** | `test_08_unauthorized_caller_issuance` | 开启 `CAD_REQUIRE_AUTHORITY_KEY=1`，未提供或提供错误 Key 尝试签发凭据 | 签发函数无条件抛出 `PermissionError("Unauthorized caller...")`，阻断非法伪造 | **PASS** (耗时 0.04s) |

**测试执行汇总**: 8 passed in 0.402s, exitCode = 0.  
**结论**: 凭证安全机制已实现内存、进程、磁盘与鉴权四维闭环，**SECURITY VERIFIED (安全核验通过)**。
