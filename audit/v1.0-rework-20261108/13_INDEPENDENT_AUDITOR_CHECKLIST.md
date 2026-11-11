# 独立审计员快速复核指南与核验清单 (13_INDEPENDENT_AUDITOR_CHECKLIST.md)

**报告编号**：REWORK-V1.0-13-AUDITOR-CHECKLIST  
**目标受众**：后续介入的独立第三方安全与工程审计员  
**编写角色**：实施方自检 (IMPLEMENTER SELF-REVIEW)  
**设计目标**：提供最小化、可复现、严格只读的独立复核路径与命令清单

---

## 一、环境与 Git 基准只读复核

```powershell
# 1. 确认工作区与 Git 基准 HEAD
Set-Location "D:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin"
git rev-parse HEAD
# 预期输出: 7d70bc090d5cef146ac3946bb062667ae30a4cc9

# 2. 检查当前 Git 变更状态（无任何 commit 或 tag）
git status -s

# 3. 检查 Node 与 Python 解释器版本
node -v
# 预期输出: v24.21.0
& "D:\SWCAD-MCP\Python313\python.exe" --version
# 预期输出: Python 3.13.16
```

---

## 二、交付物与物证完整性校验 (SHA-256 Manifest)

```powershell
# 执行清单哈希批量自检
& "D:\SWCAD-MCP\Python313\python.exe" -B -c "
import hashlib, os
from pathlib import Path
manifest = Path('audit/v1.0-rework-20261108/manifests/SHA256_MANIFEST.txt')
for line in manifest.read_text(encoding='utf-8').splitlines():
    if not line.strip() or line.startswith('#'): continue
    expected, rel_path = line.strip().split(maxsplit=1)
    target = Path('audit/v1.0-rework-20261108') / rel_path
    if not target.exists():
        print(f'MISSING: {rel_path}')
        continue
    actual = hashlib.sha256(target.read_bytes()).hexdigest().upper()
    print(f'[{actual == expected.upper()}] {rel_path}')
"
```

---

## 三、离线核心安全与单元测试复现 (全部用例应 100% PASS)

```powershell
# 1. 运行 P0 级安全回归测试 (SEC-01 ~ SEC-09)
& "D:\SWCAD-MCP\Python313\python.exe" -B tests/security_regression_test.py

# 2. 运行 Nonce 128-bit 熵与多线程并发防重放测试 (19 项对抗攻击测试)
& "D:\SWCAD-MCP\Python313\python.exe" -B tests/inspector_adversarial_attack_test.py

# 3. 运行 Stage 5 CAD 上下文测试 (核验 9 项测试与路径对齐)
& "D:\SWCAD-MCP\Python313\python.exe" -B tests/stage5_cad_context_test.py
& "D:\SWCAD-MCP\Python313\python.exe" -B tests/cad_task_context_test.py

# 4. 运行 Node.js 策略与沙箱测试 (27 项)
node --test tests/policy.test.js

# 5. 运行打包干净度与泄露扫描测试 (12 项)
node --test tests/package.test.js
```

---

## 四、SolidWorks 实机物证只读检查

为避免破坏测试现场或触发额外开销，审计员可优先通过**只读方式**核查已生成的物理物证：

1. **检查模型文件与物理尺寸**：
   - 路径：`audit/v1.0-rework-20261108/cad_e2e_sandbox/`
   - `v10_stepped_shaft.SLDPRT` (93,747 B)
   - `v10_stepped_shaft.STL` (123,184 B)
   - `v10_base.SLDPRT` (87,006 B)
   - `v10_gear.SLDPRT` (95,564 B)
   - `v10_assembly.SLDASM` (93,822 B)
   - `v10_assembly.step` (132,874 B, AP214)
   - `v10_drawing.SLDDRW` (122,971 B)
   - `v10_drawing.pdf` (54,521 B, 4 视图矢量图)
2. **检查原始执行日志与 JSON 结构**：
   - 原始日志：`audit/v1.0-rework-20261108/logs/e2e_solidworks_raw.log`
   - 结构化汇总：`audit/v1.0-rework-20261108/cad_e2e_sandbox/v10_rework_e2e_summary.json`
3. *(可选)* **在确保无用户 SolidWorks 会话的前提下重新运行实机 E2E**：
   ```powershell
   & "D:\SWCAD-MCP\Python313\python.exe" -B tests/real_cad/run_v10_rework_e2e.py
   ```

---

## 五、候选安装包真实解包与导入检查

```powershell
# 1. 核验压缩包哈希与大小
Get-FileHash -Path "dsh-solidworks-0.2.0.tgz" -Algorithm SHA256
# 预期哈希: E39A69803ABC6771B1E4C3531673380ACC7E297B9D1BD72EA476514487EF9CDC
# 预期大小: 1,500,965 字节

# 2. 独立沙箱解包核查 (临时目录)
$testDir = New-Item -ItemType Directory -Path "$env:TEMP\audit_pack_check"
tar -xzf "dsh-solidworks-0.2.0.tgz" -C $testDir
node -e "import('$testDir/package/lib/index.js').then(m => console.log('Loaded:', Object.keys(m)))"
Remove-Item -Recurse -Force $testDir
```

---

## 六、独立审计员签署区

| 审计核验维度 | 独立审计员评语 | 裁定 (PASS / FAIL / BLOCKED) | 签署日期 |
|:---|:---|:---:|:---:|
| **P0-01 实机物证与几何精度** |  |  |  |
| **P0-02 Stage 5 缺陷闭环** |  |  |  |
| **P0-03 HMAC/Nonce 安全防护** |  |  |  |
| **P0-04 文档生命周期防误删** |  |  |  |
| **P1-01 全量测试矩阵 (321项)** |  |  |  |
| **P1-02 安装包完整性与干净度** |  |  |  |
| **P1-03 物理备份还原可信度** |  |  |  |
| **P1-04 历史 CAD 特征物证** |  |  |  |
| **独立最终裁定** |  |  |  |
