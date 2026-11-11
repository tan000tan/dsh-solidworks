# 安全回归与对抗性测试验证报告

**报告编号**：AUDIT-V1.0-06-SEC-TESTS  
**执行日期**：2026-11-08  
**运行环境**：Python 3.13.16 / Node.js v24.21.0  
**综合结论**：所有 24 项 Python 安全对抗用例与 27 项 Node 策略用例全部通过（通过率 100%）

---

## 一、Python 安全回归测试矩阵 (`tests/security_regression_test.py`)

运行命令：
```powershell
D:\SWCAD-MCP\Python313\python.exe tests/security_regression_test.py
```

### 测试用例与执行结果明细：

| 用例 ID | 测试名称 | 验证目标 | 状态 | 耗时 |
|:---|:---|:---|:---:|:---:|
| **SEC-01** | `test_user_doc_protection` | 验证用户未保存模型及外部文档在任何情况下不得被关闭 | **PASS** | 0.012s |
| **SEC-02** | `test_isolated_session_lifecycle` | 验证自动化会话生命周期只登记并处置自己创建的会话文档 | **PASS** | 0.009s |
| **SEC-03** | `test_process_isolation_and_tracking` | 验证 SolidWorks 进程 PID 追踪隔离与安全接管逻辑 | **PASS** | 0.008s |
| **SEC-04** | `test_nonce_replay_prevention` | 验证 HMAC 评测凭证一次性消费及重放攻击拦截 | **PASS** | 0.007s |
| **SEC-05** | `test_path_traversal_prevention` | 验证目录穿越（`../` 及绝对跨盘路径）拦截 | **PASS** | 0.010s |
| **SEC-06** | `test_destructive_command_interception` | 验证 `CloseAllDocuments(True)`、强制杀进程等高危指令拦截 | **PASS** | 0.008s |
| **SEC-07** | `test_close_documents_schema_no_force_discard` | 验证 MCP Schema 彻底剔除 `force_discard` 参数 | **PASS** | 0.009s |
| **SEC-08** | `test_close_documents_requires_explicit_target` | 验证必须显式指定文档，禁止自动回退至 `ActiveDoc` | **PASS** | 0.011s |
| **SEC-09** | `test_is_document_owned_strict_session_check` | 验证白名单路径文件未注册时拒绝视为当前会话文档 | **PASS** | 0.008s |

**统计**：9 tests passed, 0 failed, 0 errors (耗时: 0.082s)

---

## 二、对抗性渗透与签名攻击测试矩阵 (`tests/inspector_adversarial_attack_test.py`)

运行命令：
```powershell
D:\SWCAD-MCP\Python313\python.exe tests/inspector_adversarial_attack_test.py
```

### 对抗性测试覆盖：

1. **ADV-01 签名篡改测试**：修改评测分数后签名验证立即失效并告警（拦截成功）。
2. **ADV-02 Nonce 重放攻击测试**：使用相同 Nonce 第二次提交评测报告被拦截（拦截成功）。
3. **ADV-03 Nonce 碰撞高熵测试**：并发与亚毫秒提交生成随机盐，不发生碰撞（拦截成功）。
4. **ADV-04 时间戳超期测试**：伪造过期报告由于时效校验被拒绝（拦截成功）。
5. **ADV-05 未来时间戳欺骗**：恶意注入未来时间戳被时间窗口拦截（拦截成功）。
6. **ADV-06 签名截断与注入测试**：截断 HMAC 签名或注入填充字符无法通过时序安全比对（拦截成功）。
7. **ADV-07 空秘钥攻击**：秘钥为空或 None 时强制抛出安全异常（拦截成功）。
8. **ADV-08 字典暴力破解阻断**：弱秘钥检测与长度限制（拦截成功）。
9. **ADV-09 载荷结构篡改**：向已签名 JSON 载荷注入额外元数据字段导致签名失效（拦截成功）。
10. **ADV-10 动态秘钥隔离**：不同环境变量或随机秘钥实例之间签名互不相通（拦截成功）。
11. **ADV-11 异常浮点数与 NaN 注入**：质量评测指标注入非数字被类型模型拦截（拦截成功）。
12. **ADV-12 超长字符溢出攻击**：超长字符串载荷被安全截断与校验处理（拦截成功）。
13. **ADV-13 时序攻击防护**：使用 `hmac.compare_digest` 抵抗时序侧信道分析（验证通过）。
14. **ADV-14 权限边界绕过**：尝试假冒内置 Inspector 身份调用签名被拦截（拦截成功）。
15. **ADV-15 消费 Nonce 集合溢出测试**：长周期会话安全维护 Nonce 集合大小，内存受控（验证通过）。

**统计**：15 tests passed, 0 failed, 0 errors (耗时: 0.124s)

---

## 三、Node.js 安全策略执行测试 (`tests/policy.test.js`)

运行命令：
```powershell
npm.cmd test --prefix "D:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin"
```

### 关键测试覆盖（节选）：
- `policy.test.js`: 27 个测试用例
  - 高危进程创建拦截（`powershell -enc`, `cmd /c del` 等）
  - 路径访问白名单限制（仅允许插件工作区与临时沙箱）
  - 环境变量隔离测试
  - MCP 工具调用鉴权拦截

**统计**：27/27 passed。

---

## 四、安全测试总结

所有涉及会话隔离、所有权确认、接口暴露、签名安全、进程防护的自动化测试用例均 100% 通过。无任何遗留安全失败项。
