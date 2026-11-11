# HMAC 签名与 Nonce 防重放安全复核报告 (05_HMAC_NONCE_SECURITY_REVIEW.md)

**报告编号**：REWORK-V1.0-05-HMAC-NONCE  
**执行角色**：实施方自检 (IMPLEMENTER SELF-REVIEW)  
**核查结论**：**PASS**（128-bit 随机熵、线程安全互斥、容量防 DoS 与秘钥轮换全面达标）

---

## 一、P0-03 安全整改专项核验表

| 复核要求项 | 源码落地位置 | 实现方案与参数 | 验证测试/结果 |
|:---|:---|:---|:---:|
| **1. Nonce 随机值 $\ge 128$ bit** | `cad_quality_inspector.py:75` | 使用 `secrets.token_hex(16)`（16 字节 = 32 位十六进制 = 128 bit 密码学安全随机熵） | `test_16_nonce_entropy_at_least_128_bit` (**PASS**) |
| **2. 并发消费的原子性与线程安全** | `cad_quality_inspector.py:122` | 引入 `_NONCE_LOCK = threading.Lock()`，核验与消费放入 `with _NONCE_LOCK:` 临界区 | `test_17_concurrent_consumption_thread_safety` (**PASS**) |
| **3. Nonce 过期清理与容量防 DoS** | `cad_quality_inspector.py:27` | 设 `MAX_CONSUMED_NONCES = 10000`；`_purge_expired_nonces` 每次校验前自动清理过期记录并 LRU 淘汰 | `test_18_nonce_cache_capacity_and_expired_purge` (**PASS**) |
| **4. 进程重启与会话隔离** | `cad_quality_inspector.py:33` | 进程未注入全局秘钥时，随机生成 `secrets.token_hex(32)`，进程重启后秘钥自然重置，历史凭据无法跨会话伪造 | `test_07`, `test_09` (**PASS**) |
| **5. 运行时动态秘钥轮换** | `cad_quality_inspector.py:37` | 暴露 `rotate_benchmark_secret(new_secret)`，支持在线秘钥轮换，旧会话凭据验签立即失效 | `test_19_secret_rotation_invalidation` (**PASS**) |
| **6. 签发者权限边界隔离** | `server.py` & `dsh-plugin.json` | `issue_benchmark_credential` 仅为内部算法库函数，**绝不作为 `@mcp.tool` 对外暴露**，普通 MCP 客户端无法调用签发 | 静态 Schema 扫描 (**PASS**) |

---

## 二、并发对抗性渗透测试实测证据

在 `tests/inspector_adversarial_attack_test.py` 中增加了针对高并发竞争的极限测试：
- **测试方法**：并发启动 10 个线程，同时携带同一份合法权威凭据请求消费核验。
- **实测结果**：
  - 成功消费次数：**恰好 1 次**
  - 被拦截次数：**9 次**（全部拦截信息包含 `"Replay attack intercepted: nonce ... was already used"`）
  - 杜绝了多线程竞争下的重放穿透漏洞。
