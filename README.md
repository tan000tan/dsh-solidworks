[![Release](https://img.shields.io/badge/version-0.3.2-blue.svg)](https://github.com/tan000tan/dsh-solidworks)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL%203.0-green.svg)](LICENSE)
[![SolidWorks](https://img.shields.io/badge/SolidWorks-2020%7E2026-orange.svg)](docs/FEATURE_MATRIX.md)
[![Platform](https://img.shields.io/badge/Platform-Windows%20x64-lightgrey.svg)](docs/USER_GUIDE.md)

# dsh-solidworks

> **dsh-solidworks** is an enterprise-grade AI CAD plugin designed for **DeepSeek Harness (DSH)** and standard MCP clients that bridges conversational AI directly to your local SolidWorks desktop session. Control SolidWorks using intuitive natural language, automate 3D parametric modeling, execute safe dimension adjustments, and enjoy atomic transaction rollbacks for risk-free CAD workflows.

- **Plugin Package**: `dsh-solidworks` — AGPL-3.0-only
- **Execution Engine**: `solidworks-automation-skill` Python MCP server (MIT, vendored under `vendor/`, see `NOTICE`)
- **Chinese Documentation (中文文档)**: 详细中文技术文档与极简指南参见 [README.zh.md](./README.zh.md)。

---

## ⚡ Key Highlights

- **Zero-Friction Automated Lifecycle**: One-click setup (`npm run setup`), comprehensive diagnostics (`npm run doctor`), safe upgrade with auto-backups (`npm run upgrade`), and non-destructive uninstaller (`npm run uninstall`).
- **Natural Language CAD**: Tell the AI what you want in plain words; it plans feature graphs, builds parametric geometry, and drives SolidWorks in real-time.
- **Fail-Safe Shadow Backup**: Every geometric modification is safeguarded by atomic shadow backups. If an operation fails or causes a rebuild error, your model is losslessly restored in sub-second time.
- **Double-Precision Physical Verification**: Geometry/volume checks verified in pre-expiration SolidWorks 2026 baseline runs (`<= 0.0003 mm³` / `<= 4.7e-4` relative delta across `27/71` covered tools); post-unification live SW re-run is currently blocked by local Student Edition expiration (`L5-BLOCK-01`).
- **Zero-Trust Policy Gate**: Three runtime policy tiers (`read-only`, `standard`, `full`) with strict path confinement, host-native `ctx.approval` interactive human authorization (`solidworks_confirm` self-approval is disabled / `SELF_APPROVAL_PROHIBITED`), and `SW_LOCK_WAIT_TIMEOUT_SECONDS` fast-fail isolation against modal/Head-of-Line stalls.

---

## 🚀 Quick Start (Zero-Configuration Installation)

No manual Python path tuning, environment variable editing, or manual DLL registration is required.

### 1. Prerequisites
- **Operating System**: Windows 10/11 x64
- **SolidWorks**: Desktop versions 2020–2026 (activated and launched at least once)
- **Node.js**: v22.12+ (`engines.node >=22.12`)
- **Python**: 3.10+ x64 (installed on your system)

### 2. One-Click Setup
Open your terminal in the plugin directory and run:

```cmd
npm run setup
```

The setup script automatically:
1. Detects system Node.js and Python 3.10+ environments.
2. Creates an isolated local virtual environment (`.venv`).
3. Installs all required packages (`mcp`, `pydantic`, `pywin32`, `comtypes`, etc.) silently with idempotency.
4. Invokes `pywin32_postinstall.py` to register SolidWorks COM automation interfaces.
5. Registers the plugin into your active DSH profile via `dsh_adapter.js` (to emit a standalone direct MCP client config only when explicitly needed, run `node scripts/generate_mcp_config.js --write-direct-config`).

### 3. Run System Doctor
Verify your environment at any time using the 12-dimensional health check:

```cmd
npm run doctor
```

All checks will report green `[✔ PASS]` when your machine is ready to drive SolidWorks.

---

## 🔌 Connecting to DeepSeek Harness (DSH)

### Generate Configuration Automatically
To seamlessly hook this plugin into your DeepSeek Harness or any standard MCP client, run:

```cmd
npm run mcp-config
```

This outputs a validated MCP configuration block tailored to your local environment.

### Standard MCP Client JSON Configuration Example
For standalone MCP hosts (such as Claude Desktop or custom agents):

```json
{
  "mcpServers": {
    "solidworks-cad": {
      "command": "C:\\Users\\User\\dsh-solidworks-plugin\\.venv\\Scripts\\python.exe",
      "args": [
        "C:\\Users\\User\\dsh-solidworks-plugin\\vendor\\solidworks-automation-skill\\mcp-server\\server.py"
      ],
      "env": {
        "DSH_ALLOWED_ROOTS": "[\"C:\\\\Users\\\\User\\\\Documents\\\\SolidWorks_Models\"]",
        "PYTHONUNBUFFERED": "1"
      }
    }
  }
}
```

---

## 🛠 Command Summary

| Command | Description |
| :--- | :--- |
| `npm run setup` | Automatically configure virtual environment & register COM |
| `npm run setup -- --optional` | Install optional DFM manufacturing & Office report extensions |
| `npm run doctor` | Run comprehensive 12-point system diagnostic |
| `npm run upgrade` | Auto-backup existing configs and perform safe incremental upgrade |
| `npm run uninstall -- --dry-run` | Preview safe cleanup targets (never touches your CAD assets) |
| `npm run uninstall -- --yes` | Perform non-destructive cleanup of plugin runtimes |
| `npm test` | Run core offline test suite (85 assertions across 4 offline suites; `npm run test:all`: 201 assertions across 20 suites including 42 Python suites) |

---

## 📚 Documentation Index

- 📖 **[User Guide (普通用户指南)](docs/USER_GUIDE.md)**: Step-by-step setup and conversational CAD examples.
- 🛠 **[Troubleshooting Guide (排障手册)](docs/TROUBLESHOOTING.md)**: Practical solutions for COM permissions, dialog blocking, and network mirrors.
- 📊 **[Feature Matrix (功能支持矩阵)](docs/FEATURE_MATRIX.md)**: Detailed maturity roadmap across all 13 CAD features, assemblies, and drawings.
- 📝 **[Changelog (版本变更日志)](CHANGELOG.md)**: Milestone records and historical evolution.
