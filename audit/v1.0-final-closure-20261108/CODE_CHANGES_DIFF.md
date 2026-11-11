# dsh-solidworks 深度排查与修复代码变更清单 (Code Changes Diff)

**审查基线**：`7d70bc090d5cef146ac3946bb062667ae30a4cc9`  
**整改时间**：2026-11-08  
**归档目录**：`audit/v1.0-final-closure-20261108/`

---

## 一、核心变更文件总览

| 文件路径 | 修改性质 | 修复目标与安全价值 |
| :--- | :---: | :--- |
| `vendor/solidworks-automation-skill/mcp-server/server.py` | 源码加固 | 重构 `_active_model_required`，默认 `must_be_owned=True`，严禁操作未登记的外部文档；导出白名单路径校验函数 |
| `vendor/solidworks-automation-skill/scripts/sw_connect.py` | 源码加固 | 1. 解决 `scripts.sw_connect` 与 `sw_connect` 双重导入导致的状态分裂问题；<br>2. `save_document` 增加磁盘现有文件授权校验与内存新建工程图派生所有权追踪；<br>3. `validate_path_against_allowed_roots` 兼容 JSON 数组与标准路径格式；<br>4. `close_owned_solidworks` 优雅关闭文档再调用 ExitApp |
| `docs/stage5_advanced_ai_cad/scripts/cad_quality_inspector.py` | 源码修复 | 1. 修复 `_purge_expired_nonces` 误删未过期记录的逻辑缺陷；<br>2. 修复 `verify_benchmark_credential` 密钥在模块导入期被固化的缺陷，支持动态密钥获取；<br>3. 增加 Nonce 达到容量上限时的 fail-closed 防爆防洪保护 |
| `tests/real_cad/run_v10_rework_e2e.py` | 测试代码加固 | 1. 彻底移除 `taskkill /PID ... /F`，改用全生命周期优雅退出与超时轮询；<br>2. 修复 STEP AP214 协议检测为大小写不敏感匹配；<br>3. 引入 B-Rep 实体结构深度验证（`MANIFOLD_SOLID_BREP`、`CLOSED_SHELL`、`ADVANCED_FACE`）；<br>4. 增加工程图保存前的所有权显式登记 |
| `tests/stage5_cad_context_test.py` | 测试重构 | 彻底消除此前引用别名导致的 9 个用例虚报与 double-counting，完整编写 9 个覆盖状态机跃迁、边界阻断、文档跟踪与审计轨迹的真实独立测试 |
| `tests/security_regression_test.py` | 测试扩展 | 扩充至 12 个测试用例，增加针对活动文档未授权拦截、MCP 变异工具安全门禁及白名单授权校验的真实回归用例 |
| `tests/package.test.js` 依赖环境与 NOTICE | 打包与合规 | 1. 清除 `vendor/` 下全部 `__pycache__` 字节码垃圾；<br>2. 消除 `security_regression_test.py` 中泄露的构建机个人绝对路径；<br>3. 确保 NOTICE 中声明的 190 个 vendored files 与实际物理文件数严格一致 |

---

## 二、核心模块关键代码修改详情

### 1. `vendor/solidworks-automation-skill/scripts/sw_connect.py`

#### (1) 模块单例保护（消除 Python Dual Import Trap）
```python
import sys
# 保证 scripts.sw_connect 与 sw_connect 指向同一个模块单例，防止跨模块状态分裂
if __name__ == "sw_connect" and "scripts.sw_connect" not in sys.modules:
    sys.modules["scripts.sw_connect"] = sys.modules[__name__]
elif __name__ == "scripts.sw_connect" and "sw_connect" not in sys.modules:
    sys.modules["sw_connect"] = sys.modules[__name__]
```

#### (2) `save_document` 安全鉴权与工程图派生所有权识别
```python
    existing_path = str(get_com_member(model, "GetPathName") or "").strip()
    if existing_path:
        if not is_document_owned(model, path=existing_path):
            raise PermissionError("DEF-SEC-01: Existing document is not owned by current session. Refusing save.")
    else:
        if not is_document_owned(model):
            curr_title = str(get_com_member(model, "GetTitle") or "").strip()
            is_derived = any(owned in curr_title for owned in _SESSION_OWNED_DOCUMENTS if len(owned) >= 3)
            if is_derived:
                register_owned_document(model)
            else:
                raise PermissionError("DEF-SEC-01: Document is not owned by current automation session.")
```

#### (3) `validate_path_against_allowed_roots` 双模解析
```python
    env_roots = os.environ.get("DSH_ALLOWED_ROOTS")
    is_dsh_env = env_roots is not None
    if is_dsh_env and allowed_roots is None:
        try:
            allowed_roots = json.loads(env_roots)
            if isinstance(allowed_roots, str):
                allowed_roots = [allowed_roots]
        except Exception:
            if ";" in str(env_roots) or "," in str(env_roots):
                import re
                allowed_roots = [p.strip() for p in re.split(r"[;,]", env_roots) if p.strip()]
            elif str(env_roots).strip():
                allowed_roots = [str(env_roots).strip()]
            else:
                allowed_roots = []
```

---

### 2. `vendor/solidworks-automation-skill/mcp-server/server.py`

#### `_active_model_required` fail-closed 所有权校验
```python
def _active_model_required(doc_path: Optional[str] = None, title: Optional[str] = None, must_be_owned: bool = True):
    _load_automation_modules()
    sw, model = connect_solidworks(wait_seconds=1)
    target = None
    if doc_path:
        target = sw.GetOpenDocumentByName(doc_path)
    elif title:
        target = sw.GetOpenDocumentByName(title)

    if target is None:
        target = getattr(sw, "ActiveDoc", None) or model

    if target is None:
        raise RuntimeError("No active SolidWorks document. Use solidworks_open_document or solidworks_new_document first.")

    if must_be_owned:
        from scripts.sw_connect import is_document_owned
        if not is_document_owned(target):
            doc_title = get_com_member(target, "GetTitle", default="Unknown")
            raise PermissionError(
                f"DEF-SEC-01: Document '{doc_title}' is not owned by the current automation session "
                "or resides outside allowed sandbox roots. Direct operations on unowned user documents "
                "are strictly prohibited to prevent data loss or unauthorized modifications."
            )
    return sw, target
```

---

### 3. `docs/stage5_advanced_ai_cad/scripts/cad_quality_inspector.py`

#### (1) 修复 Nonce 清理漏洞（仅清理真过期记录，容量饱和阻断）
```python
def _purge_expired_nonces(now: float) -> None:
    global _CONSUMED_NONCES
    expired = [k for k, exp in _CONSUMED_NONCES.items() if exp < now]
    for k in expired:
        _CONSUMED_NONCES.pop(k, None)

def verify_benchmark_credential(credential: Dict[str, Any], secret_key: Optional[str] = None) -> Tuple[bool, str]:
    now = time.time()
    _purge_expired_nonces(now)
    if len(_CONSUMED_NONCES) >= MAX_CONSUMED_NONCES:
        return False, "DEF-SEC-NONCE-EXHAUSTED: Nonce tracker capacity reached, failing closed"

    actual_secret = secret_key if secret_key is not None else get_benchmark_secret()
    # ...
```

---

### 4. `tests/real_cad/run_v10_rework_e2e.py`

#### (1) 彻底根除 `taskkill`，实现优雅关闭与超时轮询
```python
    # 彻底杜绝 taskkill /PID ... /F
    closed_cleanly = False
    for attempt in range(10):
        time.sleep(1)
        procs_after = list_solidworks_processes()
        if pid not in procs_after:
            closed_cleanly = True
            break
        log(f"等待 PID={pid} 正常终止... (轮询第 {attempt+1}/10 秒)")

    if closed_cleanly:
        log(f"PID={pid} 已优雅退出，系统纯净待机基线已恢复。")
    else:
        log(f"WARNING: PID={pid} 在超时时间内未退出，记录环境异常。")
```

#### (2) STEP AP214 协议检测与 B-Rep 实体核验
```python
    step_lower = step_text.lower()
    step_protocol = "UNKNOWN"
    if "automotive_design" in step_lower or "ap214" in step_lower:
        step_protocol = "AP214 (automotive_design)"
    elif "config_control_design" in step_lower or "ap203" in step_lower:
        step_protocol = "AP203"

    manifold_count = step_text.count("MANIFOLD_SOLID_BREP")
    closed_shell_count = step_text.count("CLOSED_SHELL")
    adv_face_count = step_text.count("ADVANCED_FACE")
```
