# STAGE 04 第二轮独立证据清册与密码学校验索引
# AUDIT_ROUND2_EVIDENCE_INDEX.md

**审计项目：** `dsh-solidworks` DSH 插件  
**审计阶段：** STAGE 04 — CAD 核心建模能力 (证据物证索引)  
**审计团队：** 第三方独立技术审计组  
**加密算法：** SHA-256 (不可伪造防篡改基准)  
**时间戳：** 2026-11-06T11:08:00Z  
**状态：** **INDEXED & LOCKED**

---

## 一、第二轮审计核心报告矩阵密码学指纹

| 文件相对路径 | 报告主题定位 | SHA-256 密码学指纹 |
| :--- | :--- | :--- |
| `docs/stage4_core_cad/AUDIT_ROUND2_EXECUTIVE_SUMMARY.md` | 执行摘要与最终裁定书 | `BB422600326452AB61773506563274A65A0008C3427D24B813843240EE7283C0` |
| `docs/stage4_core_cad/AUDIT_ROUND2_REQUIREMENT_TRACEABILITY.md` | 24项需求第二轮穿透核对表 | `D8D0D3A22C66B3A0C869CB89B5925A427A51434F505C7FD605E58C66A5679EF6` |
| `docs/stage4_core_cad/AUDIT_ROUND2_PATTERN_FEATURES.md` | 圆周阵列与镜像特征专项审计 | `1DA66E5E549E485E89D1BF35ECF559C31C020B28C58480D543458E5947638E6F` |
| `docs/stage4_core_cad/AUDIT_ROUND2_GEOMETRY_VERIFICATION.md` | 七大模型微观尺寸与壁厚核验 | `26E0C793FDCEBE763B6BEA63F389E6D94F290478215082FDF92DAFA317F99EB8` |
| `docs/stage4_core_cad/AUDIT_ROUND2_VERIFIER_REVIEW.md` | 第一轮核验器自身盲区审计 | `85638B9F305C1208AB0F0C0627827136505C64392DA07F3A604A83BEDD74AD39` |
| `docs/stage4_core_cad/AUDIT_ROUND2_DSH_E2E.md` | DSH 端到端四级能力分级复核 | `B7E267AEE5C1EB09497506B8358301F6CB420DEFDEEC0CC3FD9E85B0F616DBBF` |
| `docs/stage4_core_cad/AUDIT_ROUND2_SW_VERSION.md` | 2024 vs 2026 SP4.1 版本真相溯源 | `A1FC1B617E31CE6FC85F1AB756A80A9C00450B8CF2AE0BAC32EDC5823DF2C08D` |
| `docs/stage4_core_cad/AUDIT_ROUND2_TOOL_INVENTORY.md` | 73项工具全量分类对照清册 | `53C1773D8D363810D66852EC2CE0393948A583E06DE8D32AEAED484FF360F613` |
| `docs/stage4_core_cad/AUDIT_ROUND2_SELF_HEALING.md` | 自审、阻断、回滚与自愈辨析 | `8D21A2C2CCBB1E4AFBF4E4AF3D0639C3324BCCB59AD9B8B050872D602D820558` |

---

## 二、测试脚本与不可伪造物理物证指纹

| 文件相对路径 | 物证性质 | 证据等级 | SHA-256 密码学指纹 |
| :--- | :--- | :---: | :--- |
| `tests/real_cad/audit_stage4_independent_verifier.py` | 独立几何只读度量脚本 | E4 | `A4F08803BD662E115033DFF0AEA11FA0570F7184106A76B4D05CA2F5C0DB4632` |
| `tests/real_cad/sandbox/stage4_core/audit_independent_verification_evidence.json` | 独立几何复核物证 | E4 | `AA52C1396D36AB9FBE7E8A4DD2BEF16FD707B03A46BB432CCCAE6A42F1D88518` |
| `tests/real_cad/sandbox/stage4_core/stage4_benchmark_evidence.json` | 开发者基准建模实测物证 | E4 | `D02F31CECB3ED19A820F1848A14467FB8599553C49B20EFA69F69907ADBD1CDE` |
| `tests/real_cad/sandbox/phase4_core/phase4_modeling_evidence.json` | 物理回滚实体清零物证 | E4 | `6C89349E47D4B85E554D6EC4E09695C1D4F1AE71E21ACF7BE6F0F25E76DA6A66` |
| `tests/real_cad/sandbox/phase4_core/dsh_phase4_e2e_evidence.json` | DSH 端到端 One-Shot 授权物证 | E3 | `9E8940620250314ECE6C25D467BD36168091B9A6DA8A8C0A994946A0C0FBA4A5` |

---

## 三、证据等级与满足度评估总表

| 能力领域 | 要求的证据等级 | 实测最高等级 | 实测测试结果 | 真实测试局限 | 原始验收满足度 |
| :--- | :---: | :---: | :--- | :--- | :---: |
| **二维草图绘制** | E4 | **E4** | PASS (相对误差 $< 10^{-8}$) | 样条控制点精度未极限压测 | **满足** |
| **草图几何约束** | E4 | **E4** | PASS (零死坐标 `sgFIXED`) | 约束求解依赖 SW 黑盒 | **满足** |
| **实体拉伸与切除** | E4 | **E4** | PASS (法向控制精准) | 无 | **满足** |
| **旋转凸台与倒角** | E4 | **E4** | PASS (Model B 成功) | 无 | **满足** |
| **特征级圆周阵列** | E4 | **E4** | PASS (单独调用成功) | 主模型套件中未被作为主流程 | **部分满足** |
| **特征级镜像** | E4 | **E1** | **FAIL (实机调用报错崩塌)** | Mark 传错且基准面未多语言适配 | **不满足** |
| **参数化联动重建** | E4 | **E4** | PASS (体积形变增长) | 缺少装配级全局方程式广播 | **满足** |
| **特征树物理回滚** | E4 | **E4** | PASS (实体与体积清零) | 仅能回滚，不能自动修复 | **满足** |
| **DSH 宿主端到端** | E4 | **E3** | PASS (单任务法兰闭环) | 缺少复杂长链任务自主规划物证 | **部分满足** |
| **全局自审与自愈** | E4 | **E1/E4** | PARTIAL (质检与阻断可用) | **自动修复未实现 (E0)** | **不满足** |

---

## 四、第二轮证据索引总结

本证据清册客观反映了第四阶段的真实工程边界：
- 基础建模（草图、拉伸、切除、旋转、倒角、回滚、只读阻断、单次参数联动）具备坚实的 E4 级实机物理物证；
- 高阶特征（特征级镜像）、复杂交互（DSH 长链稳定规划）与闭环自愈（自动修复）存在明确的未完成或断裂；
- 所有证据均附带 SHA-256 密码学指纹，严禁后验修改。
