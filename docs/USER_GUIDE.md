# dsh-solidworks-plugin 普通用户极简使用指南

欢迎使用 `dsh-solidworks-plugin`！本插件让您无需掌握复杂的 SolidWorks COM API，只需在 DeepSeek Harness (DSH) 或 Claude 桌面端中用自然语言对话，即可驱动本地 SolidWorks 完成三维零件建模、尺寸参数自愈调整、工程图生成与格式转换。

---

## 一、系统配置前置要求

1. **操作系统**：Windows 10 / 11 64位系统 (x64)；
2. **SolidWorks**：本地已安装 SolidWorks 2020 ~ 2026 任意桌面版，并至少启动过一次；
3. **Node.js**：建议安装 Node.js >= 18.0.0 LTS（[官网下载](https://nodejs.org/)）；
4. **Python**：系统中安装有 64位 Python 3.10 ~ 3.13（若未安装，安装程序会给予明确提示）。

---

## 二、普通用户“三步极简安装”

无需繁琐的手动配环境，直接在插件主目录打开 PowerShell 或 CMD 终端：

### 第一步：一键构建虚拟环境与依赖
```bash
npm run setup
```
- **国内网络加速**：若因网络原因下载依赖慢，可运行带镜像源指令：
  ```bash
  npm run setup -- --tsinghua
  ```
- **可选高级制造扩展**：若需要生成 DFM 制造分析或 Excel 报表：
  ```bash
  npm run setup -- --optional
  ```

### 第二步：系统健康自检（确保 100% 绿灯）
```bash
npm run doctor
```
系统将自动检查 Python 运行时、Windows COM 注册状态、SolidWorks 在线心跳等指标。全部通过即可放心使用！

### 第三步：获取 MCP 接入配置
```bash
npm run mcp-config
```
控制台将输出专属的 JSON 配置片段，并自动同步写入到本目录下的 `dsh-mcp-config.json`。

---

## 三、接入 DSH 或 AI 客户端

将生成的 JSON 内容填入您的 DSH 或 Claude 客户端 MCP 配置文件中（例如 `claude_desktop_config.json` 或 DSH Profile）：

```json
{
  "mcpServers": {
    "solidworks-cad": {
      "command": "D:\\Agent工作区\\DeepSeek Harness工作区\\dsh-solidworks-plugin\\.venv\\Scripts\\python.exe",
      "args": [
        "D:\\Agent工作区\\DeepSeek Harness工作区\\dsh-solidworks-plugin\\vendor\\solidworks-automation-skill\\mcp-server\\server.py"
      ],
      "env": {
        "DSH_ALLOWED_ROOTS": "[\"D:\\\\Agent工作区\\\\DeepSeek Harness工作区\\\\dsh-solidworks-plugin\\\\测试代码\\\\sandbox_benchmark\"]",
        "PYTHONUNBUFFERED": "1"
      }
    }
  }
}
```

---

## 四、自然语言 CAD 交互示例

连接成功后，您只需在聊天框输入日常语言：

1. **新建基准零件**：
   > “帮我建一个 100x60x20mm 的钢制安装底板，中心开一个直径 20mm 的贯穿通孔。”
2. **参数修改与自愈**：
   > “把刚刚那个底板的厚度从 20mm 改成 30mm，并检查体积变化。”
   *(插件会自动抓取影子快照，修改成功后自动重建；若遇到几何自交或拓扑报错，将自动 100% 无损回滚，绝不破坏您的文件)*
3. **几何质量核算**：
   > “读取当前模型的质量属性、表面积和包围盒尺寸。”
4. **格式导出**：
   > “将当前模型导出为标准 STEP 格式保存到沙箱目录中。”

---

## 五、维护、升级与安全卸载

- **日常升级**：当有新版本时，直接在终端运行：
  ```bash
  npm run upgrade
  ```
  *(升级前会自动将您的旧配置快照备份至 `config-backups/` 目录，升级后自动触发健康验收)*
- **安全清理与卸载**：
  ```bash
  # 演练预览清理清单
  npm run uninstall -- --dry-run

  # 执行安全清理
  npm run uninstall -- --yes
  ```
  *(安全保证：仅清理插件临时虚拟环境，**100% 严格保留**您的所有 CAD 零件图纸资产)*
