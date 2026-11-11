# 阶段 0 审计：Release 资产完整性与哈希一致性审查报告 (release-integrity.md)

**审计编号：** `AUDIT-PHASE0-RELEASE-INTEGRITY-20261111`  
**审计目标：** 逐一校验 GitHub 线上正式 Release 附件与本地构建交付物的物理大小、SHA-256 哈希值，确保分发介质 100% 真实无损。

---

## 一、GitHub Release 线上资产元数据

- **Release 页面：** `https://github.com/tan000tan/dsh-solidworks/releases/tag/v0.3.0`
- **Release 标题：** `v0.3.0: Official Productization Release & Multi-Version Support`
- **关联 Tag：** `v0.3.0` (关联 Commit: `1eb2bdf63f9bb3207e8df46927708e16d3f1ee5e`)
- **发布时间：** 2026-11-11T02:24:42Z (本地时间 10:24)

---

## 二、三端资产与 SHA-256 哈希比对表

比对三端：
1. **GitHub 线上 Release Assets**；
2. **本地候选交付目录 (`v0.3.0-final-release-candidate/`)**；
3. **官方清单文件 (`SHA256清单.txt`)**。

| 序号 | 资产文件名 | 线上文件大小 | 本地文件大小 | 磁盘文件实测 SHA-256 哈希 | 官方清单标称 SHA-256 哈希 | 一致性比对结论 |
|---|---|---|---|---|---|---|
| 1 | `dsh-solidworks-0.3.0.tgz` (npm 源码归档包) | 7,652,536 字节 | 7,652,536 字节 | `85DAD498432DAEB063F806C41E64AAB1364DEE01D0AF494D4DC485B06E6962BC` | `85dad498432daeb063f806c41e64aab1364dee01d0af494d4dc485b06e6962bc` | **100% 严密吻合** |
| 2 | `dsh-solidworks-v0.3.0-windows-installer.zip` (正式 Windows 安装包) | 8,013,239 字节 | 8,013,239 字节 | `68EE95802A5322758A51878391F3F955B86ED06A720AF67D1FFE1D21ABF27EA0` | `68ee95802a5322758a51878391f3f955b86ed06a720af67d1ffe1d21abf27ea0` | **100% 严密吻合** |
| 3 | `v0.3.0-e2e-cad-and-diagnostics-evidence.zip` (全量验证原始证据包) | 9,317 字节 | 9,317 字节 | `58716FDE9176F9C26474E8BA8375E0258B7C29B86340573AE812A02C8C59A0F2` | `58716fde9176f9c26474e8ba8375e0258b7c29b86340573ae812a02c8c59a0f2` | **100% 严密吻合** |

---

## 三、安装包解压与内容无损校验

对 `dsh-solidworks-v0.3.0-windows-installer.zip` 进行只读结构解析：
- **核心文件总数：** 677 个物理文件；
- **批处理入口完整性：**
  - `install.bat` (一键安装部署入口)
  - `doctor.bat` (一键系统健康诊断)
  - `upgrade.bat` (平滑升级向导)
  - `uninstall.bat` (安全卸载与清理)
- **底层核心库完备性：**
  - `package.json`, `dsh-plugin.json`, `cordis.patch.yml` 元数据完整；
  - `vendor/solidworks-automation-skill/` 包含 71 个 CAD 核心脚本，无 `.pyc` 字节码或构建临时文件污染；
  - 授权许可证文件 `LICENSE` (AGPL-3.0) 与 `NOTICE` 完好附带。

核查判定：**PASS (Release 资产未发生任何网络损坏或文件篡改，哈希完全一致)**。
