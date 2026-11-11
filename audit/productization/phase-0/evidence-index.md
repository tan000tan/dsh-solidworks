# 阶段 0 审计：阶段 0 证据索引清单 (evidence-index.md)

**审计编号：** `AUDIT-PHASE0-EVIDENCE-INDEX-20261111`  
**审计基准：** `tan000tan/dsh-solidworks` 分支 `feat/v0.3.0-phase1-6` (Commit: `1eb2bdf`)

---

## 一、阶段 0 核心审计报告文件清单

| 报告文件名 | 存放路径 | 核心审查范围 | 审计判定 |
|---|---|---|---|
| `baseline.md` | `audit\productization\phase-0\baseline.md` | 基准版本、分支、HEAD、Release、Tag 与市场状态四维度区分 | **PASS / BLOCKED** |
| `repository-state.md` | `audit\productization\phase-0\repository-state.md` | 工作区现场、4 个未提交文件审查、未跟踪目录、元数据一致性 | **PASS** |
| `release-integrity.md` | `audit\productization\phase-0\release-integrity.md` | GitHub Release 资产大小、三端哈希一致性比对 (100% 吻合) | **PASS** |
| `marketplace-state.md` | `audit\productization\phase-0\marketplace-state.md` | 官方市场条目 yml、PR #14130 合并状态、平台限制与下载地址 | **PASS** |
| `permissions-audit.md` | `audit\productization\phase-0\permissions-audit.md` | Git Credential 暴露风险、OS 隔离状态审查与硬性写封印 | **FAIL (OS隔离) / PASS (安全封印)** |
| `evidence-index.md` | `audit\productization\phase-0\evidence-index.md` | 阶段 0 证据文件与审计结论总览索引 | **PASS** |

---

## 二、关键外部存证哈希比对总览

```
[Release 资产 1]
文件名: dsh-solidworks-0.3.0.tgz
大小: 7,652,536 字节
SHA-256: 85DAD498432DAEB063F806C41E64AAB1364DEE01D0AF494D4DC485B06E6962BC

[Release 资产 2]
文件名: dsh-solidworks-v0.3.0-windows-installer.zip
大小: 8,013,239 字节
SHA-256: 68EE95802A5322758A51878391F3F955B86ED06A720AF67D1FFE1D21ABF27EA0

[Release 资产 3]
文件名: v0.3.0-e2e-cad-and-diagnostics-evidence.zip
大小: 9,317 字节
SHA-256: 58716FDE9176F9C26474E8BA8375E0258B7C29B86340573AE812A02C8C59A0F2
```

---

## 三、停止规则执行确认

本阶段只读审计已**全部执行完成**：
1. 没有修改任何产品源码；
2. 没有删除或恢复任何文件；
3. 没有执行任何 Git Commit、Push、Tag、Release 或 PR 操作；
4. 没有关闭用户正在使用的 SolidWorks 实例；
5. 已将完整的真实性审计结果、差异与安全边界完整呈报用户，**当前执行立即停止，等待用户审阅与下一步决策**。
