# 质量检查器防伪安全整改与对抗攻击审计报告 (09_QUALITY_INSPECTOR_SECURITY.md)

## 1. 漏洞背景与第三轮审查事实 (DEF-05)

在第三轮独立取证审计中，审计人员通过构造如下攻击代码：
```python
forged_theoretical = dict(measured)
forged_theoretical["provenance"] = "independent_analytical"
```
成功使质量检查器给出了 `VERIFIED`、100 分且无任何告警的通过结论。

### 根因分析
1. **信任边界崩溃**: 原检查器将调用方传入的明文字符串字段（`provenance` 与 `source`）作为免检通行证。当检测到克隆内容时，只要包含指定的明文字符串，便直接跳过克隆拦截。
2. **缺乏独立验签机制**: 普通 Python 字典属于不可信输入层，在未经过独立密码学签名或代数推导绑定的情况下，被赋予了过高信任。

---

## 2. 第四轮防伪架构重构实现

依据第四轮任务书要求，彻底重构了 `docs/stage5_advanced_ai_cad/scripts/cad_quality_inspector.py` 的防伪内核：

### 2.1 核心防护规则
1. **明文字段彻底脱敏与特权剥夺**:
   - 彻底删除基于 `provenance` 或 `source` 字符串的免检逻辑。
   - 任何在普通输入字典中携带的明文来源标签，均被降级处理并记录安全告警，绝不授予免检特权。
2. **全维度克隆与数据重复硬拦截**:
   - 对 `measured` 与 `theoretical` 字典进行核心度量字段比对。
   - 浅拷贝 (`dict(meas)`)、深拷贝 (`copy.deepcopy(meas)`)、字典重构 (`{k: v for k, v in meas.items()}`)，以及所有共享数值完全按位重合的情况，一律触发 **克隆攻击拦截 (Clone Attack Intercepted)**。
   - 一旦触发克隆拦截，几何项得分直接赋 **0.0 分**，状态直接判定为 **`FAILED`**，绝不给及格或未验证缓冲。
3. **密码学权威基准凭据系统 (`BenchmarkCredential`)**:
   - 引入不可伪造的基准凭据模型：
     ```python
     class BenchmarkCredential(BaseModel):
         issuer: str = "cad_benchmark_authority"
         model_id: str                      # 强绑定被检测模型唯一 ID
         issued_at: float                   # 签发时间戳
         expires_at: float                  # 过期时间戳 (TTL 窗口控制)
         nonce: str                         # 单次随机盐，防重放
         volume_analytical_mm3: float       # 代数解析推导理论值
         payload_hash: str                  # SHA-256 载荷哈希
         signature: str                     # HMAC-SHA256 密钥签名
     ```
   - **重放防护**: 凭据包含精确时间戳与有效时间窗口，超过有效期立即判定为过期重放攻击并拒绝。
   - **跨模型盗用防护**: 凭据严格绑定 `model_id`；若将零件 B 的凭证用于零件 A，核验立即失败。
   - **内容防篡改**: 对 `model_id + volume + timestamps + nonce` 联合计算 SHA-256 哈希并以服务端根密钥签名。篡改任何数值都会导致验签失败。
4. **未认证理论源降级**:
   - 若调用方仅传入无签名的普通外部理论字典（且非克隆），检查器判定其缺少权威推导背书，明确标记为 **`NOT_VERIFIED`**，得分封顶 60 分，综合报告 `is_acceptable` 严禁为 `True`。

---

## 3. 对抗性攻击测试实测全集 (15 项全绿证据)

编写专项对抗攻击测试套件 `tests/inspector_adversarial_attack_test.py`，完整覆盖任务书规定的全部攻击向量与合法基准对照：

```
测试文件: tests/inspector_adversarial_attack_test.py
执行时间: 2026-11-06 22:15:08
执行结果: Ran 15 tests in 1.053s, OK (100% 拦截率)
```

| 编号 | 攻击场景类别 | 攻击实施方法 | 检查器防御表现与实测结论 | 防御状态 |
| :--- | :--- | :--- | :--- | :--- |
| **ATK-01** | **浅拷贝伪造** | `theo = dict(meas)` | 命中浅拷贝克隆规则，得分 0.0，判定 `FAILED`。 | **BLOCKED (PASS)** |
| **ATK-02** | **深拷贝伪造** | `theo = copy.deepcopy(meas)` | 命中深拷贝克隆规则，得分 0.0，判定 `FAILED`。 | **BLOCKED (PASS)** |
| **ATK-03** | **字典重构伪造** | `{k: v for k, v in meas.items()}` | 提取核心键值比对完全相同，得分 0.0，判定 `FAILED`。 | **BLOCKED (PASS)** |
| **ATK-04** | **修改 provenance** | `theo = dict(meas); theo["provenance"] = "independent_analytical"` | 剥夺明文字符串特权，依然命中克隆检测，得分 0.0，判定 `FAILED`。 | **BLOCKED (PASS)** |
| **ATK-05** | **修改 source** | `theo = dict(meas); theo["source"] = "analytical"` | 明文字段忽略并告警，依然判定克隆攻击，得分 0.0，判定 `FAILED`。 | **BLOCKED (PASS)** |
| **ATK-06** | **修改模型 ID** | 截取模型 `other_bracket_99` 的合法凭证套用于 `stepped_shaft` | 凭据绑定核验失败 (`Model ID mismatch`)，得分 0.0，判定 `FAILED`。 | **BLOCKED (PASS)** |
| **ATK-07** | **伪造时间戳** | 构造过期时间戳凭据 (`expires_at = now - 10`) | 命中时效校验 (`Credential expired`)，得分 0.0，判定 `FAILED`。 | **BLOCKED (PASS)** |
| **ATK-08** | **伪造测量结果** | 凭证内直接篡改 `volume=999999` 未重新签名 | 载荷哈希比对失败 (`Payload hash mismatch`)，得分 0.0，判定 `FAILED`。 | **BLOCKED (PASS)** |
| **ATK-09** | **重放旧凭据** | 延迟等待凭据超过 TTL 窗口后重新提交 | 拦截过期凭证，阻断重放，得分 0.0，判定 `FAILED`。 | **BLOCKED (PASS)** |
| **ATK-10** | **跨模型凭证混淆** | 用阶梯轴的合法凭证提交到齿轮模型的质检流程 | 发现 `model_id` 与被测模型不匹配，得分 0.0，判定 `FAILED`。 | **BLOCKED (PASS)** |
| **ATK-11** | **缺失凭据** | 传入普通无签名数值字典（非克隆） | 判定理论来源无法证实，得分封顶 60 分，判定 `NOT_VERIFIED`。 | **BLOCKED (PASS)** |
| **ATK-12** | **篡改凭据签名** | 将凭据签名替换为伪造随机字符串 (`deadbeef...`) | HMAC-SHA256 签名校验失败，得分 0.0，判定 `FAILED`。 | **BLOCKED (PASS)** |
| **ATK-13** | **相同数据直接克隆** | 构造不同 key 结构但 volume/surface_area 按位相同的字典 | 共享数值特征重合拦截，得分 0.0，判定 `FAILED`。 | **BLOCKED (PASS)** |
| **ATK-14** | **同一内存对象** | `meas is theo` (传入同一字典引用) | 命中指针同一性拦截，得分 0.0，判定 `FAILED`。 | **BLOCKED (PASS)** |
| **BEN-15** | **合法基准核验** | 由权威机构签发凭证，且实测网格与理论值具备真实工程微差 (0.474%) | 密码学验签通过，误差符合工程规范，判定 `VERIFIED`，得分 >= 85。 | **VERIFIED (PASS)** |

---

## 4. 结论与验收状态

- **DEF-05 最终验收裁定**: **`VERIFIED`**
- 成功构建了基于密码学基准凭证 (`BenchmarkCredential`) 与多维数值独立性检测的防伪防御体系。
- 攻击者仅修改普通输入字典，**绝无任何可能**将不可信数据伪装为可信数据。
