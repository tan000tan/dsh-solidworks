# dsh-solidworks-plugin (AI CAD 插件)

[![Release](https://img.shields.io/badge/version-0.2.0-blue.svg)](https://github.com/tan000tan/dsh-solidworks)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL%203.0-green.svg)](LICENSE)
[![SolidWorks](https://img.shields.io/badge/SolidWorks-2020%7E2026-orange.svg)](docs/FEATURE_MATRIX.md)
[![Platform](https://img.shields.io/badge/Platform-Windows%20x64-lightgrey.svg)](docs/USER_GUIDE.md)

让 DeepSeek Harness (DSH) 或任意标准 MCP 客户端直接驱动本地 **SolidWorks** 桌面完成三维建模、自愈式尺寸修改、质量属性复核、工程图出图与格式转换的 AI CAD 插件。

---

## 一、核心特性

- 🚀 **小白友好，一键就绪**：彻底废弃繁琐的环境配置说明书，提供纯 Node.js 驱动的 `setup`、`doctor`、`upgrade`、`uninstall` 全套自动化基建，防 PowerShell 执行策略拦截。
- 🛡 **影子事务与自愈回滚**：内置 `ShadowBackupManager` 机制，在尺寸修改或复杂建模前自动抓取物理只读快照。若发生几何报错或拓扑自交，**0.5 秒内自动无损回滚**，绝不破坏用户原本文件。
- 📐 **双精度质量属性验收**：拒绝浅层 API Mock！本插件所有核心特征均经过真实 SolidWorks 2026 物理环境实机打火验证，理论体积与实测体积误差 **$\le 0.0003\text{ mm}^3$**。
- 🔒 **严密安全防护策略**：默认只读模式（read-only），高风险写操作逐次授权（Fail-Closed），内建 Windows 桌面 STA 消息隔离与系统窗口防误杀白名单。

---

## 二、三步极简快速开始

### 1. 自动化安装环境
在插件目录打开终端运行：
```bash
npm run setup
```
*(国内用户若网络受限，可附加 `--tsinghua` 参数使用清华镜像源加速)*

### 2. 全项健康体检
```bash
npm run doctor
```
系统将自动执行 8 大核心维度诊断（Python/COM/SolidWorks心跳/STA桌面权限/沙箱读写等），确保 100% 绿灯。

### 3. 获取 MCP 接入配置
```bash
npm run mcp-config
```
将生成的标准 JSON 配置填入您的 DSH 或 Claude 客户端即可开始对话建模！

---

## 三、常用日常指令

| 指令 | 作用说明 |
| :--- | :--- |
| `npm run setup` | 自动化创建隔离虚拟环境并注册 pywin32 COM 组件 |
| `npm run setup -- --optional` | 安装 DFM 制造分析与 Office 报表扩展依赖 |
| `npm run doctor` | 系统全项健康诊断，输出 PASS/WARN/FAIL |
| `npm run upgrade` | 自动快照备份旧配置并平滑升级依赖 |
| `npm run uninstall -- --dry-run` | 演练预览安全卸载清理范围（绝不触碰用户 CAD 模型） |
| `npm run uninstall -- --yes` | 执行安全卸载清理 |
| `npm test` | 运行离线自动化测试套件 (63 项断言) |

---

## 四、文档索引

- 📖 **[普通用户极简使用指南 (User Guide)](docs/USER_GUIDE.md)**：包含完整图文流程与自然语言对话实例；
- 🛠 **[故障排查与自愈手册 (Troubleshooting)](docs/TROUBLESHOOTING.md)**：常见 Windows COM 权限、网络与弹窗排障方案；
- 📊 **[CAD 功能支持矩阵 (Feature Matrix)](docs/FEATURE_MATRIX.md)**：13 项建模特征、装配体、工程图成熟度标定；
- 📝 **[版本变更日志 (CHANGELOG)](CHANGELOG.md)**：v0.2.0 里程碑技术演进细节。

---

## 五、开源许可证

- 插件宿主与管理层遵循 [AGPL-3.0-only](LICENSE) 协议；
- 内嵌自动化技能核心位于 `vendor/` 遵循 [MIT](vendor/solidworks-automation-skill/LICENSE) 协议，详见 [NOTICE](NOTICE)。
