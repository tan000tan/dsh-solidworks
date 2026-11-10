# 第五阶段底层依赖准入控制与安全隔离矩阵 (Stage 5 Dependency Matrix)

> **文档编号：** `S5-DOC-04-DEPENDENCY-MATRIX`  
> **归档路径：** `docs/stage5_advanced_ai_cad/STAGE5_DEPENDENCY_MATRIX.md`  
> **编制依据：** 《AUDIT-R2-11-DEPENDENCY-VERIFICATION-MATRIX》与项目安全约束  

---

## 一、准入控制强制铁律

为了防止上层研发继承未经独立验证的脆弱能力或陷入历史缺陷陷阱，第五阶段研发团队必须严格遵守以下四条铁律：

1. **绝对准入铁律 (VERIFIED Only)：** 只有标记为 `VERIFIED` 的底层能力，才允许作为第五阶段端到端主干流程的核心依赖；
2. **受限调用铁律 (PARTIAL With Guard)：** 标记为 `PARTIAL` 的能力只能在明确边界限制下辅助调用，必须配置超时、参数校验与异常捕获防护网；
3. **隔离禁用铁律 (BLOCKED Absolute Ban)：** 凡标记为 `BLOCKED` 的功能（如 `solidworks_mirror_feature` 和虚假自愈系统），**严禁在第五阶段代码中直接或间接调用**；
4. **测试独立性铁律：** 第五阶段的所有新模块测试必须自给自足，不得因底层尚未修复的历史缺陷而掩盖或降低自身的测试断言难度。

---

## 二、底层能力依赖准入与隔离清单

| 依赖模块 / API | 底层验证状态 | 第五阶段使用策略 | 替代或兜底技术方案 |
|:---|:---:|:---|:---|
| **拉伸凸台 (`extrude_boss`)** | **VERIFIED** | 允许主干调用，作为实体成型核心 | 无需替代，可直接构建 |
| **拉伸切除 (`extrude_cut`)** | **VERIFIED** | 允许主干调用，作为减材成型核心 | 无需替代，可直接构建 |
| **旋转凸台与切除 (`revolve_boss/cut`)** | **VERIFIED** | 允许主干调用，作为车削方案核心 | 无需替代，可直接构建 |
| **圆角与倒角 (`fillet/chamfer`)** | **VERIFIED** | 允许调用，由优化器自动排布至终饰时序 | 优化器在拓扑排序中自动后置 |
| **圆周阵列 (`circular_pattern`)** | **PARTIAL** | 限制调用，仅在轴向基准明确时使用 | 若选择器不确定，可降级为参数化多孔草图 |
| **镜像特征 (`mirror_feature`)** | **BLOCKED** | **完全禁用！严禁调用！** | **强制使用草图对称约束或独立几何特征替代** |
| **FeatureGraph IR 数据模型** | **VERIFIED** | 允许继承，作为方案和树优化的中间格式 | 引入扩展属性支持多方案比对 |
| **Kahn 拓扑排序算法** | **VERIFIED** | 允许继承，作为确定性时序调度核心 | 增加终饰特征权重微调机制 |
| **CADGraphExecutor 物理执行** | **VERIFIED** | 允许继承，作为物理调度执行底座 | 增加执行进度事件回调接口 |
| **物理逆序回滚 (Level 3)** | **VERIFIED** | 允许继承，作为建模失败撤销机制 | 结合快照管理器提供双重保护 |
| **尺寸依赖图 (`dimension_ir`)** | **VERIFIED** | 允许继承，作为迭代影响域分析底座 | 增加参数敏感性分析方法 |
| **参数安全修改 (`modify_dimension_safe`)**| **VERIFIED** | 允许继承，作为增量迭代执行底座 | 修改后必须触发 ForceRebuild3 校验 |
| **自动自愈算法** | **BLOCKED** | **完全禁用！严禁宣传！** | **采用“影响分析 -> 物理撤销 -> 重新规划”显式闭环替代** |
| **装配体与配合底层 API** | **PARTIAL** | 隔离研发，规划层闭环，物理实测限隔离环境 | 优先在内存建立 AssemblyGraph 约束拓扑 |
| **质量属性核验器 (`inspector`)** | **PARTIAL** | 限制使用，必须外挂坐标微观点采样 | S5-E 自建坐标采样器弥补盲区 |

---

## 三、代码级防御实现与拦截守卫

在第五阶段核心模块中，设置统一的前置防御守卫：

```python
def check_feature_admission(feature_type: str) -> None:
    """第五阶段底层依赖准入拦截守卫"""
    BLOCKED_FEATURES = {
        "solidworks_mirror_feature": "镜像特征存在严重 API 传参缺陷与崩溃风险 (DEF-11)，禁止调用！",
        "auto_self_heal": "虚假自愈系统已被审计推翻 (DEF-12)，禁止调用！"
    }
    if feature_type in BLOCKED_FEATURES:
        raise PermissionError(f"[S5-ADMISSION-BLOCKED] {BLOCKED_FEATURES[feature_type]}")
```
该守卫在多方案规划和特征树优化过程中强制生效，确保缺陷接口无法侵入新系统。
