# 既有清理与验收报告真实性审计：全量证据索引清单 (evidence-index.md)

**审计编号：** `AUDIT-PREFLIGHT-EVIDENCE-INDEX-20261111`  
**审计基准：** `tan000tan/dsh-solidworks` 分支 `feat/v0.3.0-phase1-6` (Commit: `1eb2bdf`)

---

## 一、原始物理文件与测试证据索引

| 证据类别 | 物理文件路径 | 生成时间 | 核心验证内容 | 核查状态 |
|---|---|---|---|---|
| **CAD 物理闭环原始日志** | `temp_evidence_v030_compat\D-Real-CAD-Regression\comprehensive_cad_closure.json` | 2026-11-11 10:35:48 | SW 2026 物理建模、凸台 50000 mm³、切除 46858.4073 mm³、22 节点树、双路径质量、四维文档守恒 (0 -> 0) | **PASS** |
| **CAD 闭环控制台日志** | `temp_evidence_v030_compat\D-Real-CAD-Regression\comprehensive_cad_closure.log` | 2026-11-11 10:36:04 | 完整的 CAD 操作执行文本输出与计时 | **PASS** |
| **Node 端到端 CAD 闭环证据** | `e2e_full_chain_cad_loop.json` | 2026-11-11 10:35:46 | Node -> MCP -> Python -> COM -> SolidWorks 全链路调用状态 | **PASS** |
| **系统 12 维健康自检报告** | `diagnostic-report.json` | 2026-11-11 13:10:58 | 12 项系统级自检结构化数据 (passCount: 12) | **PASS** |
| **系统健康诊断可读文档** | `diagnostic-report.md` | 2026-11-11 13:10:58 | 针对普通用户的健康自检 Markdown 报告 | **PASS** |
| **多版本降级矩阵原始日志** | `temp_evidence_v030_compat\C-Compat-Matrix-Tests\sw_compat_matrix_deep_verification.json` | 2026-11-11 13:10:58 | 19 项多版本降级与几何异常分类断言记录 | **PASS** |
| **安全对抗与策略防护日志** | `temp_evidence_v030\E-Security-and-Safety\policy_security_adversarial_test.json` | 2026-11-11 13:07:12 | 路径遍历、TTL 过期、参数防篡改、设备文件名拦截 | **PASS** |
| **沙箱安装与生命周期日志** | `temp_evidence_v030\C-Installation-and-Environment\installation_and_lifecycle_verification.json` | 2026-11-11 10:33:58 | 干净沙箱自动部署、依赖创建、MCP 挂载与安全卸载 | **PASS** |
| **Token 紧凑压缩压测日志** | `temp_evidence_v030\F-Performance-and-UX\token_and_ux_benchmark.json` | 2026-11-11 13:09:00 | Schema 压缩 69.41%、1000 次压力测试延迟评估 | **PASS** |

---

## 二、被清理目录涉及的历史归档包索引

| 归档包文件名 | 存储物理路径 | 长度 (字节) | 真实 SHA-256 哈希 | 状态 |
|---|---|---|---|---|
| `dsh-solidworks-0.1.0.tgz` | `<WORKSPACE_ROOT>\dsh-solidworks-0.1.0.tgz` | 641,457 | `9C8746061415C394E25AF18CCCC900078D9D257D5E75F7559FA4889FACA2A1F3` | **完好存证** |
| `dsh-solidworks-0.2.0.tgz` (根目录) | `<WORKSPACE_ROOT>\dsh-solidworks-0.2.0.tgz` | 1,353,150 | `12DD5073A2CEC8862B361B31DD3303A7808E8636B9E6066D49408ACBCCAE6FB5` | **完好存证** |
| `dsh-solidworks-0.2.0.tgz` (审计目录) | `<WORKSPACE_ROOT>\audit\v1.0-round2-closure-20261109\dist\dsh-solidworks-0.2.0.tgz` | 1,353,150 | `12DD5073A2CEC8862B361B31DD3303A7808E8636B9E6066D49408ACBCCAE6FB5` | **完好存证** |

---

## 三、当前 v0.3.0 正式候选分发资产与 SHA-256 索引

交付物存储目录：`<WORKSPACE_ROOT>\v0.3.0-final-release-candidate\`

| 序号 | 交付物文件名 | 物理大小 (字节) | 磁盘文件真实 SHA-256 哈希 | 清单标称哈希 | 比对结果 |
|---|---|---|---|---|---|
| 1 | `01_最终验收与产品化交付主报告.md` | 16,929 | `471C7BF4D63D22634F12C0249E46DD43802F2A8FDB6FBD8A1328E5AB0CBC56EE` | `471c7bf4...` | **100% 吻合** |
| 2 | `02_普通用户安装部署与配置指南.md` | 11,544 | `601365A1BD98DF7CD85030CC1E7A95E714FFC69C51DF09D40CBEE3F77223CCB1` | `601365a1...` | **100% 吻合** |
| 3 | `03_平滑升级与配置回滚指南.md` | 9,876 | `1CD5519612E1E2A7503DE3E52C56C94F3003DA9053E893DE1892759D3DE899ED` | `1cd55196...` | **100% 吻合** |
| 4 | `04_安全卸载与残留清理指南.md` | 8,912 | `6A7DC120719D164D7C8FA48DF5C7703C91046226643D6889B937A57C5F0AAF14` | `6a7dc120...` | **100% 吻合** |
| 5 | `05_系统健康诊断与排障指南.md` | 10,233 | `2BDDB91AAA5E8542E2147D0C5FA43AD6FEAFBA5381C0B419C97224773D7C5B9D` | `2bddb91a...` | **100% 吻合** |
| 6 | `06_SolidWorks多版本兼容矩阵与验收说明.md` | 12,450 | `6C743CA1BCD808DB1F74B50BFC585F5FC128A2CCFEE021B4F6717794F38805BF` | `6c743ca1...` | **100% 吻合** |
| 7 | `dsh-solidworks-v0.3.0-windows-installer.zip` | 8,013,239 | `68EE95802A5322758A51878391F3F955B86ED06A720AF67D1FFE1D21ABF27EA0` | `68ee9580...` | **100% 吻合** |
| 8 | `v0.3.0-e2e-cad-and-diagnostics-evidence.zip` | 9,317 | `58716FDE9176F9C26474E8BA8375E0258B7C29B86340573AE812A02C8C59A0F2` | `58716fde...` | **100% 吻合** |
| 9 | `dsh-solidworks-0.3.0.tgz` | 7,652,536 | `85DAD498432DAEB063F806C41E64AAB1364DEE01D0AF494D4DC485B06E6962BC` | `85dad498...` | **100% 吻合** |

---

## 四、外部线上状态与存证链接

1. **GitHub 官方 Release 资产：**
   - Release URL: `https://github.com/tan000tan/dsh-solidworks/releases/tag/v0.3.0`
   - Tag: `v0.3.0` (Commit: `1eb2bdf63f9bb3207e8df46927708e16d3f1ee5e`)
   - 线上 3 项资产大小与哈希与本地候选包 100% 一致。
2. **DSH 官方市场 PR：**
   - PR URL: `https://github.com/awesome-dsh-plugin/awesome-dsh-plugin/pull/14130`
   - 状态：`closed / merged: true` (合并于 2026-11-11T03:25:29Z)
   - 线上索引条目：`data/plugins/tan000tan__dsh-solidworks.yml`
