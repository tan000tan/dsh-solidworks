# 全仓库 72 个物理测试文件完整执行与覆盖矩阵

- **总测试文件数**: 72
- **文件执行通过**: 53
- **文件执行失败**: 18
- **超时中断**: 1
- **累计执行用例数**: 584
- **累计通过用例数 (PASS)**: 513
- **累计失败用例数 (FAIL)**: 67
- **累计跳过用例数 (SKIP)**: 4

| 序号 | 测试文件相对路径 | 函数数 | 执行数 | PASS | FAIL | SKIP | Mock | 真实SW | 退出码 | 耗时(s) | 状态 | 日志路径 / 未执行原因 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | `tests/policy.test.js` | 27 | 27 | 27 | 0 | 0 | 否 | 否 | 0 | 0.71 | **PASS** | audit/v1.0-round2-closure-20261109/logs/tests_policy.test.js.log |
| 2 | `tests/mcp.test.js` | 13 | 13 | 13 | 0 | 0 | 否 | 否 | 0 | 1.87 | **PASS** | audit/v1.0-round2-closure-20261109/logs/tests_mcp.test.js.log |
| 3 | `tests/package.test.js` | 14 | 12 | 10 | 2 | 0 | 是 | 否 | 1 | 0.93 | **FAIL** |  |
| 4 | `tests/schema.test.js` | 0 | 1 | 1 | 0 | 0 | 否 | 否 | 0 | 0.25 | **PASS** | audit/v1.0-round2-closure-20261109/logs/tests_schema.test.js.log |
| 5 | `tests/audit.test.js` | 3 | 1 | 1 | 0 | 0 | 否 | 否 | 0 | 4.35 | **PASS** | audit/v1.0-round2-closure-20261109/logs/tests_audit.test.js.log |
| 6 | `tests/host.test.js` | 0 | 1 | 1 | 0 | 0 | 否 | 否 | 0 | 8.87 | **PASS** | audit/v1.0-round2-closure-20261109/logs/tests_host.test.js.log |
| 7 | `tests/crash.test.js` | 2 | 1 | 1 | 0 | 0 | 否 | 否 | 0 | 2.35 | **PASS** | audit/v1.0-round2-closure-20261109/logs/tests_crash.test.js.log |
| 8 | `mcp-server-solidworks-main/adapters/claude/tests/test_execution_client.py` | 2 | 2 | 2 | 0 | 0 | 否 | 否 | 0 | 2.64 | **PASS** | audit/v1.0-round2-closure-20261109/logs/mcp-server-solidworks-main_adapters_claude_tests_test_execution_client.py.log |
| 9 | `mcp-server-solidworks-main/adapters/claude/tests/test_schema_contract.py` | 2 | 2 | 2 | 0 | 0 | 否 | 否 | 0 | 2.66 | **PASS** | audit/v1.0-round2-closure-20261109/logs/mcp-server-solidworks-main_adapters_claude_tests_test_schema_contract.py.log |
| 10 | `mcp-server-solidworks-main/adapters/dsh/tests/test_job_store.py` | 3 | 3 | 3 | 0 | 0 | 否 | 否 | 0 | 2.83 | **PASS** | audit/v1.0-round2-closure-20261109/logs/mcp-server-solidworks-main_adapters_dsh_tests_test_job_store.py.log |
| 11 | `mcp-server-solidworks-main/adapters/dsh/tests/test_orchestrator.py` | 36 | 37 | 37 | 0 | 0 | 否 | 否 | 0 | 4.88 | **PASS** | audit/v1.0-round2-closure-20261109/logs/mcp-server-solidworks-main_adapters_dsh_tests_test_orchestrator.py.log |
| 12 | `mcp-server-solidworks-main/adapters/dsh/tests/test_policy.py` | 17 | 38 | 38 | 0 | 0 | 否 | 否 | 0 | 2.63 | **PASS** | audit/v1.0-round2-closure-20261109/logs/mcp-server-solidworks-main_adapters_dsh_tests_test_policy.py.log |
| 13 | `mcp-server-solidworks-main/adapters/dsh/tests/test_tool_surface.py` | 22 | 32 | 32 | 0 | 0 | 否 | 否 | 0 | 3.61 | **PASS** | audit/v1.0-round2-closure-20261109/logs/mcp-server-solidworks-main_adapters_dsh_tests_test_tool_surface.py.log |
| 14 | `mcp-server-solidworks-main/cad-planner/drawing/tests/test_draw_contract.py` | 1 | 1 | 1 | 0 | 0 | 否 | 否 | 0 | 0.2 | **PASS** | audit/v1.0-round2-closure-20261109/logs/mcp-server-solidworks-main_cad-planner_drawing_tests_test_draw_contract.py.log |
| 15 | `mcp-server-solidworks-main/compiler/solidworks/pycompiler/tests/test_compiler.py` | 73 | 73 | 73 | 0 | 0 | 否 | 否 | 0 | 0.22 | **PASS** | audit/v1.0-round2-closure-20261109/logs/mcp-server-solidworks-main_compiler_solidworks_pycompiler_tests_test_compiler.py.log |
| 16 | `mcp-server-solidworks-main/compiler/solidworks/pycompiler/tests/test_ir_schema_contract.py` | 1 | 1 | 1 | 0 | 0 | 否 | 否 | 0 | 0.15 | **PASS** | audit/v1.0-round2-closure-20261109/logs/mcp-server-solidworks-main_compiler_solidworks_pycompiler_tests_test_ir_schema_contract.py.log |
| 17 | `mcp-server-solidworks-main/tests/test_repo_consistency.py` | 3 | 3 | 3 | 0 | 0 | 否 | 否 | 0 | 0.15 | **PASS** | audit/v1.0-round2-closure-20261109/logs/mcp-server-solidworks-main_tests_test_repo_consistency.py.log |
| 18 | `tests/cad_graph_executor_test.py` | 42 | 21 | 21 | 0 | 0 | 是 | 是 | 0 | 1.02 | **PASS** | audit/v1.0-round2-closure-20261109/logs/tests_cad_graph_executor_test.py.log |
| 19 | `tests/cad_task_context_test.py` | 18 | 9 | 9 | 0 | 0 | 否 | 否 | 0 | 0.85 | **PASS** | audit/v1.0-round2-closure-20261109/logs/tests_cad_task_context_test.py.log |
| 20 | `tests/cad_task_planner_test.py` | 18 | 9 | 9 | 0 | 0 | 是 | 否 | 0 | 0.77 | **PASS** | audit/v1.0-round2-closure-20261109/logs/tests_cad_task_planner_test.py.log |
| 21 | `tests/com_worker_test.py` | 20 | 10 | 10 | 0 | 0 | 否 | 否 | 0 | 3.86 | **PASS** | audit/v1.0-round2-closure-20261109/logs/tests_com_worker_test.py.log |
| 22 | `tests/dimension_dependency_graph_test.py` | 8 | 4 | 4 | 0 | 0 | 否 | 否 | 0 | 0.58 | **PASS** | audit/v1.0-round2-closure-20261109/logs/tests_dimension_dependency_graph_test.py.log |
| 23 | `tests/dimension_manager_test.py` | 10 | 5 | 5 | 0 | 0 | 是 | 否 | 0 | 2.74 | **PASS** | audit/v1.0-round2-closure-20261109/logs/tests_dimension_manager_test.py.log |
| 24 | `tests/dimension_system_test.py` | 24 | 12 | 12 | 0 | 0 | 是 | 否 | 0 | 0.92 | **PASS** | audit/v1.0-round2-closure-20261109/logs/tests_dimension_system_test.py.log |
| 25 | `tests/engine_reliability_test.py` | 10 | 5 | 5 | 0 | 0 | 否 | 否 | 0 | 0.98 | **PASS** | audit/v1.0-round2-closure-20261109/logs/tests_engine_reliability_test.py.log |
| 26 | `tests/failure_injection_test.py` | 2 | 0 | -1 | 0 | 1 | 否 | 是 | 0 | 0.47 | **PASS** | audit/v1.0-round2-closure-20261109/logs/tests_failure_injection_test.py.log |
| 27 | `tests/feature_graph_test.py` | 12 | 6 | 6 | 0 | 0 | 否 | 否 | 0 | 2.14 | **PASS** | audit/v1.0-round2-closure-20261109/logs/tests_feature_graph_test.py.log |
| 28 | `tests/inspector_adversarial_attack_test.py` | 38 | 19 | 19 | 0 | 0 | 否 | 否 | 0 | 1.61 | **PASS** | audit/v1.0-round2-closure-20261109/logs/tests_inspector_adversarial_attack_test.py.log |
| 29 | `tests/ir_solidworks_end_to_end_test.py` | 2 | 0 | -1 | 0 | 1 | 否 | 是 | 0 | 0.79 | **PASS** | audit/v1.0-round2-closure-20261109/logs/tests_ir_solidworks_end_to_end_test.py.log |
| 30 | `tests/mcp_failure_cleanup_e2e_test.py` | 10 | 0 | -1 | 0 | 1 | 否 | 是 | 0 | 2.63 | **PASS** | audit/v1.0-round2-closure-20261109/logs/tests_mcp_failure_cleanup_e2e_test.py.log |
| 31 | `tests/mcp_mid_operation_failure_test.py` | 18 | 0 | -1 | 0 | 1 | 否 | 是 | 0 | 2.55 | **PASS** | audit/v1.0-round2-closure-20261109/logs/tests_mcp_mid_operation_failure_test.py.log |
| 32 | `tests/model_quality_inspector_test.py` | 12 | 6 | 6 | 0 | 0 | 否 | 否 | 0 | 0.76 | **PASS** | audit/v1.0-round2-closure-20261109/logs/tests_model_quality_inspector_test.py.log |
| 33 | `tests/param_extractor_test.py` | 10 | 5 | 5 | 0 | 0 | 否 | 否 | 0 | 0.26 | **PASS** | audit/v1.0-round2-closure-20261109/logs/tests_param_extractor_test.py.log |
| 34 | `tests/rem_compat_test.py` | 36 | 18 | 18 | 0 | 0 | 否 | 是 | 0 | 0.77 | **PASS** | audit/v1.0-round2-closure-20261109/logs/tests_rem_compat_test.py.log |
| 35 | `tests/rem_stress_test.py` | 76 | 38 | 38 | 0 | 0 | 否 | 是 | 0 | 2.49 | **PASS** | audit/v1.0-round2-closure-20261109/logs/tests_rem_stress_test.py.log |
| 36 | `tests/rem_user_test.py` | 20 | 10 | 10 | 0 | 0 | 否 | 否 | 0 | 2.44 | **PASS** | audit/v1.0-round2-closure-20261109/logs/tests_rem_user_test.py.log |
| 37 | `tests/remediation_cad_quality_inspector_test.py` | 22 | 11 | 11 | 0 | 0 | 否 | 否 | 0 | 0.63 | **PASS** | audit/v1.0-round2-closure-20261109/logs/tests_remediation_cad_quality_inspector_test.py.log |
| 38 | `tests/security_regression_test.py` | 24 | 12 | 12 | 0 | 0 | 是 | 是 | 0 | 2.64 | **PASS** | audit/v1.0-round2-closure-20261109/logs/tests_security_regression_test.py.log |
| 39 | `tests/shadow_backup_test.py` | 10 | 5 | 5 | 0 | 0 | 否 | 否 | 0 | 0.55 | **PASS** | audit/v1.0-round2-closure-20261109/logs/tests_shadow_backup_test.py.log |
| 40 | `tests/stage5_advanced_aicad_integration_test.py` | 8 | 4 | 4 | 0 | 0 | 否 | 否 | 0 | 0.6 | **PASS** | audit/v1.0-round2-closure-20261109/logs/tests_stage5_advanced_aicad_integration_test.py.log |
| 41 | `tests/stage5_assembly_planner_test.py` | 10 | 5 | 5 | 0 | 0 | 否 | 否 | 0 | 0.57 | **PASS** | audit/v1.0-round2-closure-20261109/logs/tests_stage5_assembly_planner_test.py.log |
| 42 | `tests/stage5_auto_iteration_test.py` | 10 | 5 | 5 | 0 | 0 | 否 | 否 | 0 | 0.57 | **PASS** | audit/v1.0-round2-closure-20261109/logs/tests_stage5_auto_iteration_test.py.log |
| 43 | `tests/stage5_cad_context_test.py` | 18 | 9 | 9 | 0 | 0 | 否 | 否 | 0 | 0.87 | **PASS** | audit/v1.0-round2-closure-20261109/logs/tests_stage5_cad_context_test.py.log |
| 44 | `tests/stage5_feature_tree_optimizer_test.py` | 10 | 5 | 5 | 0 | 0 | 否 | 否 | 0 | 0.23 | **PASS** | audit/v1.0-round2-closure-20261109/logs/tests_stage5_feature_tree_optimizer_test.py.log |
| 45 | `tests/stage5_multi_scheme_planner_test.py` | 10 | 5 | 5 | 0 | 0 | 否 | 否 | 0 | 0.59 | **PASS** | audit/v1.0-round2-closure-20261109/logs/tests_stage5_multi_scheme_planner_test.py.log |
| 46 | `tests/stage5_quality_inspector_test.py` | 12 | 6 | 6 | 0 | 0 | 否 | 否 | 0 | 0.58 | **PASS** | audit/v1.0-round2-closure-20261109/logs/tests_stage5_quality_inspector_test.py.log |
| 47 | `tests/task_state_machine_test.py` | 14 | 7 | 7 | 0 | 0 | 否 | 否 | 0 | 0.47 | **PASS** | audit/v1.0-round2-closure-20261109/logs/tests_task_state_machine_test.py.log |
| 48 | `tests/unified_dimension_migration_test.py` | 6 | 3 | 3 | 0 | 0 | 是 | 否 | 0 | 0.79 | **PASS** | audit/v1.0-round2-closure-20261109/logs/tests_unified_dimension_migration_test.py.log |
| 49 | `tests/window_recovery_test.py` | 10 | 5 | 5 | 0 | 0 | 否 | 否 | 0 | 2.31 | **PASS** | audit/v1.0-round2-closure-20261109/logs/tests_window_recovery_test.py.log |
| 50 | `tests/real_cad/run_v10_rework_e2e.py` | 1 | 8 | 8 | 0 | 0 | 否 | 是 | 0 | 211.25 | **PASS** | audit/v1.0-round2-closure-20261109/logs/tests_real_cad_run_v10_rework_e2e.py.log |
| 51 | `tests/real_cad/real_cad_advanced_features_test.py` | 6 | 6 | 0 | 6 | 0 | 否 | 是 | 1 | 0.78 | **FAIL** | Blocked by security write guard (requires explicit --authorize-cad-write) |
| 52 | `tests/real_cad/real_cad_benchmark_suite.py` | 1 | 1 | 1 | 0 | 0 | 否 | 是 | 0 | 0.8 | **PASS** | audit/v1.0-round2-closure-20261109/logs/tests_real_cad_real_cad_benchmark_suite.py.log |
| 53 | `tests/real_cad/real_cad_complex_test.py` | 2 | 2 | 0 | 2 | 0 | 否 | 是 | 1 | 0.78 | **FAIL** | Blocked by security write guard (requires explicit --authorize-cad-write) |
| 54 | `tests/real_cad/real_cad_ddg_stress_test.py` | 1 | 1 | 0 | 1 | 0 | 否 | 是 | 1 | 0.74 | **FAIL** | Blocked by security write guard (requires explicit --authorize-cad-write) |
| 55 | `tests/real_cad/real_cad_dimension_test.py` | 7 | 7 | 0 | 7 | 0 | 否 | 是 | 1 | 0.84 | **FAIL** | Blocked by security write guard (requires explicit --authorize-cad-write) |
| 56 | `tests/real_cad/real_cad_drawing_mqi_test.py` | 6 | 6 | 0 | 6 | 0 | 否 | 是 | 1 | 0.72 | **FAIL** | Blocked by security write guard (requires explicit --authorize-cad-write) |
| 57 | `tests/real_cad/real_cad_drawing_reopen_test.py` | 1 | 1 | 0 | 1 | 0 | 否 | 是 | 1 | 0.43 | **FAIL** | Script failed execution |
| 58 | `tests/real_cad/real_cad_failure_test.py` | 1 | 1 | 1 | 0 | 0 | 否 | 否 | 0 | 0.75 | **PASS** | audit/v1.0-round2-closure-20261109/logs/tests_real_cad_real_cad_failure_test.py.log |
| 59 | `tests/real_cad/real_cad_fault_injection_test.py` | 6 | 6 | 0 | 6 | 0 | 否 | 是 | 1 | 0.77 | **FAIL** | Blocked by security write guard (requires explicit --authorize-cad-write) |
| 60 | `tests/real_cad/real_cad_graph_test.py` | 1 | 1 | 0 | 1 | 0 | 否 | 是 | 1 | 0.76 | **FAIL** | Script failed execution |
| 61 | `tests/real_cad/real_cad_mechanical_parts_test.py` | 6 | 6 | 0 | 6 | 0 | 否 | 是 | 1 | 0.76 | **FAIL** | Blocked by security write guard (requires explicit --authorize-cad-write) |
| 62 | `tests/real_cad/real_cad_physical_rollback_test.py` | 1 | 1 | 0 | 1 | 0 | 否 | 是 | 1 | 0.46 | **FAIL** | Script failed execution |
| 63 | `tests/real_cad/real_cad_planner_test.py` | 6 | 6 | 0 | 6 | 0 | 否 | 是 | 1 | 0.8 | **FAIL** | Blocked by security write guard (requires explicit --authorize-cad-write) |
| 64 | `tests/real_cad/real_cad_preflight.py` | 1 | 1 | 1 | 0 | 0 | 否 | 是 | 0 | 14.17 | **PASS** | audit/v1.0-round2-closure-20261109/logs/tests_real_cad_real_cad_preflight.py.log |
| 65 | `tests/real_cad/real_cad_sketch_dimension_test.py` | 7 | 7 | 0 | 7 | 0 | 否 | 是 | 1 | 0.72 | **FAIL** | Blocked by security write guard (requires explicit --authorize-cad-write) |
| 66 | `tests/real_cad/real_cad_stress_test.py` | 3 | 3 | 0 | 3 | 0 | 否 | 是 | 1 | 0.72 | **FAIL** | Blocked by security write guard (requires explicit --authorize-cad-write) |
| 67 | `tests/real_cad/audit_stage4_independent_verifier.py` | 1 | 0 | 0 | 0 | 0 | 否 | 是 | -1 | 60.03 | **TIMEOUT** | Timed out after 60s |
| 68 | `tests/real_cad/extreme_engineering_suite.py` | 1 | 1 | 0 | 1 | 0 | 否 | 是 | 1 | 0.76 | **FAIL** | Script failed execution |
| 69 | `tests/real_cad/geometry_verifier.py` | 0 | 1 | 1 | 0 | 0 | 否 | 否 | 0 | 0.51 | **PASS** | audit/v1.0-round2-closure-20261109/logs/tests_real_cad_geometry_verifier.py.log |
| 70 | `tests/real_cad/night_07_verification.py` | 1 | 1 | 0 | 1 | 0 | 否 | 是 | 1 | 0.43 | **FAIL** | Script failed execution |
| 71 | `tests/real_cad/phase4_cad_core_suite.py` | 3 | 3 | 0 | 3 | 0 | 否 | 是 | 1 | 1.69 | **FAIL** | Script failed execution |
| 72 | `tests/real_cad/stage4_benchmark_full_suite.py` | 7 | 7 | 0 | 7 | 0 | 否 | 是 | 1 | 1.5 | **FAIL** | Script failed execution |
