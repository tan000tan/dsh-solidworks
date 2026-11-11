# dsh-solidworks 最终工作区与 Git 状态保全报告

**报告编号**: DSH-SW-GIT-FINAL-20261109  
**Git 基准 Commit**: `7d70bc090d5cef146ac3946bb062667ae30a4cc9` (commit log: `chore(vendor): vendor solidworks-automation-skill v0.1.1`)  
**状态遵从准则**: **严禁执行 `git commit`、`git tag`、`git push` 或远程发布，保留完整现场 Diff**

---

## 一、Git 状态与修改清单统计

执行 `git status -s` 与 `git diff --stat` 的统计结果如下：

### 1. 已修改受跟踪文件清单 (24 个)

`
 NOTICE                                             |    4 +-
 bin/dsh-solidworks.js                              |   28 +-
 docs/USER_GUIDE.md                                 |    6 +-
 docs/verification.md                               |    2 +-
 dsh-plugin.json                                    |   11 +-
 lib/discover.js                                    |   52 +-
 lib/index.js                                       |   12 +-
 lib/policy.js                                      |   18 +
 scripts/doctor.js                                  |    4 +-
 scripts/generate_mcp_config.js                     |   12 +-
 scripts/setup.js                                   |    5 +-
 tests/failure_injection_test.py                    |    7 +-
 tests/ir_solidworks_end_to_end_test.py             |    6 +
 tests/mcp.test.js                                  |   53 +-
 tests/mcp_failure_cleanup_e2e_test.py              |    3 +
 tests/mcp_mid_operation_failure_test.py            |   21 +-
 tests/package.test.js                              |    2 +-
 tests/probe-server.mjs                             |   18 +-
 vendor/solidworks-automation-skill/mcp-server/server.py      | 4276 +++++++++++++++++++-
 vendor/solidworks-automation-skill/scripts/cad_task_context.py |  271 +-
 vendor/solidworks-automation-skill/scripts/dimension_manager.py|  115 +-
 vendor/solidworks-automation-skill/scripts/feature_graph_ir.py |    2 +
 vendor/solidworks-automation-skill/scripts/sw_connect.py     | 1521 ++++++-
 vendor/solidworks-automation-skill/scripts/sw_native_wire.py |  266 +-
 24 files changed, 6437 insertions(+), 278 deletions(-)
`

### 2. 核心修改归因分析

1. **`vendor/.../cad_task_context.py`**:
   - 彻底修复 `DeleteSelection2(1)` 引发的模态确认弹窗死锁，替换为 `DeleteSelection2(0)`；
   - 增强逆序特征清理与事务状态机安全回滚保护。
2. **`vendor/.../sw_native_wire.py`**:
   - 增加对 `invoke_native` 的入参路径强制执行 `validate_path_against_allowed_roots` 与 `is_document_owned` 校验，阻断未受管资产越界访问。
3. **`vendor/.../server.py` & `sw_connect.py`**:
   - 实现 DEF-SEC-01 受管文档判定机制 (`_active_model_required(must_be_owned=True)`)；
   - 建立单文档受管哈希注册与安全受限关闭逻辑，彻底杜绝 `CloseAllDocuments`。
4. **`tests/...`**:
   - 统一加入 `solidworks_processes()` 待机基线守卫，确保在离线/待机测试时优雅跳过实机物理用例，防止后台遗留僵尸进程；
   - 调整实机中途注入故障测试超时阈值至 60 秒，确保大特征复杂模型重建不发生误报。
5. **`lib/policy.js` & `lib/discover.js`**:
   - 完善三级策略门禁分级，补齐 73 工具完整映射；
   - 增强路径规范化，支持物理真实路径解析、符号链接穿越拦截与 UNC 共享阻断。

---

## 二、工作区资产完整性与物理备份保障

为确保本次整改与验证的所有操作具备绝对可追溯性与可回滚性：

1. **物理备份快照已验证有效**:
   - 备份目录: `D:\Agent工作区\Backups\dsh-solidworks-plugin-backup-final-release-20261108`
   - 文件总数: 8,953 个文件，占用磁盘 47.20 MB；
   - 8 个核心关键文件（包括 `server.py`、`sw_connect.py`、`package.json` 等）已完成 SHA-256 哈希比对，证实备份 100% 完好无损。
2. **未引入任何编译垃圾或字节码污染**:
   - 工作区内所有 `__pycache__` 目录与 `*.pyc` 文件已彻底清理，当前计数为 0；
   - `tests/package.test.js` 执行全量断言通过，无任何构建机本地绝对路径泄露。

**保全结论**: 工作区修改范围高度聚焦，所有源码与测试变更均严格服务于 P0 事故闭环与 v1.0 交付标准，Git 状态与现场物理证据已完整保全。
