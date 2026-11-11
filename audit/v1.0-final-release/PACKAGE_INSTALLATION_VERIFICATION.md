# dsh-solidworks 独立纯净环境打包与安装测试验证报告

**报告编号**: DSH-SW-PKG-VERIFY-20261109  
**打包产物**: `dsh-solidworks-0.2.0.tgz`  
**测试隔离目录**: `C:\Users\Khalil\AppData\Local\Temp\dsh-install-verification\`  
**测试判定**: **全部 6 项纯净环境端到端自动化核验 100% 通过**

---

## 一、发布压缩包构建详情

在插件根目录下执行：
```powershell
& "D:\Node.js\npm.cmd" pack
```
输出指标与详情：
- **包名称**: `dsh-solidworks`
- **版本号**: `0.2.0`
- **文件名**: `dsh-solidworks-0.2.0.tgz`
- **压缩包大小**: 1.4 MB
- **解包后体积**: 4.6 MB
- **文件总数**: 452 个文件 (已完全剔除历史临时补丁脚本)
- **SHA-1 (Shasum)**: `9363f4832cc757e228790400475afedecaadf0c8`
- **完整性哈希 (Subresource Integrity)**: `sha512-Px4j0pKq803+o[...]H2YbE3jMp9w0A==`
- **零安装后钩子**: `package.json` 中无任何 `preinstall` / `postinstall` 恶意脚本，符合应用市场合规准则。

---

## 二、独立纯净环境模拟安装

在操作系统临时目录创建全新的独立工作区，模拟最终用户在无源码、无工程上下文的干净机器上安装：
```powershell
$testDir = "C:\Users\Khalil\AppData\Local\Temp\dsh-install-verification"
Set-Location $testDir
& "D:\Node.js\npm.cmd" init -y
& "D:\Node.js\npm.cmd" install "D:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin\dsh-solidworks-0.2.0.tgz"
```
**安装结果**:
```
added 1 package, and audited 2 packages in 8s
found 0 vulnerabilities
```
安装过程完全无报错、无告警、无高危漏洞，耗时仅 8 秒。

---

## 三、自动化纯净环境功能与策略核验

在隔离目录下运行自动化核验脚本 `verify_installed_plugin.mjs`，涵盖宿主交互全流程：

```powershell
$env:DSH_SOLIDWORKS_PYTHON = "D:\SWCAD-MCP\Python313\python.exe"
$env:PYTHONDONTWRITEBYTECODE = "1"
& "D:\Node.js\node.exe" verify_installed_plugin.mjs
```

### 自动化测试阶段与断言结果

1. **PASS: [1/6] 包元数据与清单一致性核验**:
   - `node_modules/dsh-solidworks/package.json` 版本号为 `0.2.0`；
   - `dsh-plugin.json` 声明的插件版本为 `0.2.0`；
   - `cordis.patch.yml` 成功包含 `dsh-solidworks` 接入定义。
2. **PASS: [2/6] ESM 规范导出核验**:
   - 动态导入 `await import('dsh-solidworks')` 成功；
   - 导出 `name === 'dsh-solidworks'`；
   - 导出 `typeof apply === 'function'`；
   - 导出 `DEFAULTS` 默认配置对象。
3. **PASS: [3/6] 只读策略门禁严格核验**:
   - 在 `mode: 'read-only'` 模式下调用 `apply(ctx)`；
   - 插件仅注册 21 个工具（2 个内置元工具 + 19 个读工具）；
   - 所有 52 个写操作与高风险操作被 100% 物理剔除，无法被 LLM 探测或调用。
4. **PASS: [4/6] solidworks_status 执行与安全诊断核验**:
   - 调用 `solidworks_status.execute({}, {})` 返回标准 JSON；
   - 报告插件名称为 `dsh-solidworks`，版本为 `0.2.0`；
   - 报告策略模式为 `read-only`；
   - 报告 FastMCP 服务端状态为 `running: true`，工具总数为 71；
   - 经全面审查，状态输出中无任何环境变量、私有凭据或绝对敏感信息泄露。
5. **PASS: [5/6] 完整模式 73 工具与 FastMCP Schema 自动提升核验**:
   - 在 `mode: 'full'` 模式下调用 `apply(ctx)`；
   - 插件注册全部 73 个工具（2 个内置元工具 + 71 个 MCP 工具）；
   - 逐一检查所有工具的 `parameters` 结构，断言其根类型为 `object`；
   - **断言无残留 `params` 包装层**（FastMCP 原生双层包装已被宿主适配器彻底平铺展开，确保 DeepSeek/Claude 等通用 LLM 能够直接根据标准参数名生成调用）。
6. **PASS: [6/6] 物理路径策略阻断与高风险口令机制核验**:
   - 测试高风险工具 `solidworks_export_active`；
   - 传入跨越沙箱的越界路径 `C:\Windows\System32\evil.step`，被策略守卫在进入 Python 服务端前直接拦截，返回 `code: 'PATH_OUTSIDE_ALLOWED_ROOTS'`；
   - 传入沙箱内的合法路径 `valid.step`（未附带口令），策略守卫拦截并返回 `code: 'CONFIRMATION_REQUIRED'`，明确指示 LLM 必须经由用户确认后调用 `solidworks_confirm`。

### 3.2 独立安装环境全局 CLI 实操断言

在纯净安装目录下对发布包导出的 `bin/dsh-solidworks` 进行全套指令实机测试：
1. **`dsh-solidworks version`**: 成功输出 `{ "name": "dsh-solidworks", "version": "0.2.0" }`，版本号 100% 同步；
2. **`dsh-solidworks doctor`**: 成功输出宿主运行态，输出 `ready: yes`，诊断 0 阻塞错误；
3. **`dsh-solidworks mcp-config`**: 成功自适应沙箱目录与解释器，生成标准的 `mcpServers.solidworks` 接入 JSON 代码段；
4. **`dsh-solidworks list-tools --mode read-only`**: 成功输出 `mode read-only: 19 published / 52 withheld of 71`，阻断 52 个写操作与高风险工具；
5. **`dsh-solidworks list-tools --mode full`**: 成功输出 `mode full: 71 published / 0 withheld of 71`，全部工具正常挂载；
6. **`dsh-solidworks call solidworks_health_check --mode read-only`**: 真实通过策略管道调用底层 MCP 工具，耗时 394 ms 返回 `status: ok`。

---

## 四、验证结论

实机安装测试证明：
发布的 `dsh-solidworks-0.2.0.tgz` 具备完全独立的自包含运行能力，在真实用户的纯净环境下安装后，元数据完备、依赖结构轻量、生命周期管理可靠、安全策略防护无漏洞，满足正式投产与发布标准。
