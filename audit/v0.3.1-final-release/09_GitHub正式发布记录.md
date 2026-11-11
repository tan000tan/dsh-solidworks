# dsh-solidworks v0.3.1 GitHub 正式发布记录

**发布编号：** `RELEASE-GITHUB-v0.3.1` (GitHub Release ID: `441453566`)  
**仓库地址：** `https://github.com/tan000tan/dsh-solidworks`  
**Release 页面：** `https://github.com/tan000tan/dsh-solidworks/releases/tag/v0.3.1`  
**发布版本：** `v0.3.1`  
**Git Tag：** `v0.3.1` (`72b8ebe2ef57cdc9cc218a335e719dbcd533199d`)  
**主分支合并提交：** `main` (`293c87f536dff962b9e3b1552a783880cbd8fafd`)  
**Release 类型：** 正式发布（Full Release，`draft: false`, `prerelease: false`）  
**时间戳：** 2026-11-11

---

## 一、发布资产清单与线上下载哈希复核

| 资产文件名称 (本地 / GitHub Release) | 大小 (Bytes) | SHA-256 校验和 (本地与线上下载 100% 一致) | 官方公开下载 URL |
| :--- | :--- | :--- | :--- |
| `dsh-solidworks-0.3.1.tgz` | 7,678,948 | `501a9655eb37c4b0651f75da6cdd9ffb8c4785eefce468724b2664522dd96785` | `https://github.com/tan000tan/dsh-solidworks/releases/download/v0.3.1/dsh-solidworks-0.3.1.tgz` |
| `dsh-solidworks-v0.3.1-windows-installer.zip` | 8,046,537 | `83dac29c88d618b48bfdd4896c6675b3d96c82caf4e15db3145a1a566958b55a` | `https://github.com/tan000tan/dsh-solidworks/releases/download/v0.3.1/dsh-solidworks-v0.3.1-windows-installer.zip` |
| `v0.3.1-e2e-cad-and-diagnostics-evidence.zip` | 13,614 | `4d714294b8d07fc12edb625d3ded3f0e647d9ec087538cd0079b95c4c23cbbef` | `https://github.com/tan000tan/dsh-solidworks/releases/download/v0.3.1/v0.3.1-e2e-cad-and-diagnostics-evidence.zip` |
| `SHA256清单.txt` (`SHA256.txt`) | 429 | `c9c718fc84758134fa50d910f5c9c27650c4c738d3f25d4bff78487cc27095b9` | `https://github.com/tan000tan/dsh-solidworks/releases/download/v0.3.1/SHA256.txt` |

---

## 二、正式 Release 公告正文 (Release Notes)

```markdown
## dsh-solidworks v0.3.1 Official Release

### 概述 (Overview)
dsh-solidworks v0.3.1 是针对 DeepSeek Harness (DSH) 生态的工业级 SolidWorks 自动化插件正式稳定版。本次发布彻底修复了此前发现的 P0 级 AI 自授权漏洞与运行环境隔离隐患，完成了针对 SolidWorks 2026 SP4.1 物理实机的全量闭环验证与 18 项极端对抗安全审计。

### 核心改进与修复 (Key Highlights)
1. **P0 人类审批体系重构 (HMAC-SHA256 票据挑战响应)：**
   - 彻底废除不可信的 `confirmedByHuman: true` 标记。
   - 实现高危写操作动态门禁：未授权操作自动拦截并签发 Challenge，必须由可信宿主通道使用内存私钥计算生成绑定参数摘要的 HMAC-SHA256 凭证。
   - 凭证单次消费即销毁，防重放、防篡改、防跨会话滥用，通过 18 项极端安全对抗测试。
2. **Python Runtime 专属隔离与零污染保证：**
   - 外部 Python 仅作为种子解释器，所有依赖安装严格限制在插件专属目录下的 `.venv` 内。
   - 物理扫描确证 DSH 全局 Primary Runtime 零写入、零污染。
3. **工具集权威对齐：**
   - 澄清统计口径：71 个 MCP 服务端 CAD 工具（19 READ, 26 WRITE, 26 HIGH）+ 2 个 DSH 宿主元工具（`solidworks_status`, `solidworks_confirm`）= 73 个正式工具。
4. **SolidWorks 2026 SP4.1 真实实机几何验证：**
   - 11 步核心 CAD 闭环测试（凸台、盲切、装配、工程图、质量核验）100% PASS，体积误差 0.0000%，四维文档守恒（0 残留）。
5. **多版本兼容矩阵：**
   - 针对 SolidWorks 2020-2026 实现了动态 API 探针与平滑降级支持。

### 校验和验证 (Package Checksums)
- `dsh-solidworks-0.3.1.tgz`: `501a9655eb37c4b0651f75da6cdd9ffb8c4785eefce468724b2664522dd96785`
- `dsh-solidworks-v0.3.1-windows-installer.zip`: `83dac29c88d618b48bfdd4896c6675b3d96c82caf4e15db3145a1a566958b55a`
```

---

## 三、Git 操作记录
- **Commit 描述：** `release: finalize v0.3.1 security hardening, runtime isolation and marketplace package`
- **Tag 名称：** `v0.3.1`
- **验证命令：** `git log -1 --stat`
- **Release 状态：** 正式归档发布。
