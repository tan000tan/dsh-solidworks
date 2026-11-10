# 第五阶段高级 AI CAD 核心模块详细设计书 (Stage 5 Module Design)

> **文档编号：** `S5-DOC-03-MODULE-DESIGN`  
> **归档路径：** `docs/stage5_advanced_ai_cad/STAGE5_MODULE_DESIGN.md`  
> **编制依据：** 《STAGE5_ARCHITECTURE.md》与各子阶段开发要求  

---

## 一、模块一：多方案自动规划与比较引擎 (`multi_scheme_planner.py`)

### 1.1 数据结构定义 (Data Models)
```python
from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class ManufacturingIntent(str, Enum):
    TURNING = "turning"           # 车削加工
    MILLING = "milling"           # 铣削加工
    CASTING_AND_MACHINING = "casting_and_machining"  # 铸造后机加工
    SHEET_METAL = "sheet_metal"   # 钣金成型

class SchemeStep(BaseModel):
    step_id: str
    feature_type: str             # extrude_boss, revolve_boss, extrude_cut, fillet, etc.
    description: str
    params: Dict[str, Any]
    dependencies: List[str] = Field(default_factory=list)

class ModelingScheme(BaseModel):
    scheme_id: str
    scheme_name: str
    manufacturing_intent: ManufacturingIntent
    steps: List[SchemeStep]
    feature_count: int
    complexity_score: float       # 0.0 ~ 10.0 (越低越紧凑)
    parametric_freedom: float     # 0.0 ~ 10.0 (越高参数化程度越高)
    rebuild_risk_score: float     # 0.0 ~ 10.0 (越低越安全)
    overall_score: float          # 加权总分 (0.0 ~ 100.0)
    selection_rationale: str

class MultiSchemePlanResult(BaseModel):
    design_goal: str
    schemes: List[ModelingScheme]
    recommended_scheme_id: str
    recommendation_summary: str
```

### 1.2 核心接口与评分算法
- **类名：** `MultiSchemePlanner`
- **核心方法：**
  - `generate_candidate_schemes(design_spec: Dict[str, Any]) -> List[ModelingScheme]`
  - `evaluate_and_rank_schemes(schemes: List[ModelingScheme]) -> MultiSchemePlanResult`
- **评分公式：**
  $$\text{Score} = 40 \times (1 - \frac{\text{Complexity}}{10}) + 35 \times \frac{\text{Freedom}}{10} + 25 \times (1 - \frac{\text{Risk}}{10})$$

---

## 二、模块二：复杂特征树规划与依赖优化器 (`complex_feature_tree_optimizer.py`)

### 2.1 拓扑优化策略
1. **终饰特征后置重排 (Late-Finishing Rule)：**
   - 自动识别 `fillet`（圆角）和 `chamfer`（倒角）特征；
   - 在 DAG 拓扑排序中，将其安全推迟至所有主成型特征（凸台/切除）构建完毕后再执行，防止过早倒角造成面引用拓扑丢失；
2. **破损特征隔离重构 (Defect Bypass Rule)：**
   - 拦截包含 `solidworks_mirror_feature` 的输入请求，将其自动重构为具有几何对等性的草图对称约束或独立特征节点。

### 2.2 核心接口
- **类名：** `ComplexFeatureTreeOptimizer`
- **核心方法：**
  - `optimize_feature_graph(raw_graph: FeatureGraphIR) -> FeatureGraphIR`
  - `detect_and_eliminate_redundancy(graph: FeatureGraphIR) -> Tuple[FeatureGraphIR, List[str]]`
  - `validate_topological_robustness(graph: FeatureGraphIR) -> bool`

---

## 三、模块三：自动迭代修改与影响分析引擎 (`auto_iteration_engine.py`)

### 3.1 影响域推导模型
```python
class ModificationImpact(BaseModel):
    target_param: str
    old_value: float
    new_value: float
    affected_features: List[str]
    affected_dimensions: List[str]
    risk_level: str               # LOW, MEDIUM, HIGH
    requires_rebuild: bool = True

class IterationDiffResult(BaseModel):
    success: bool
    modified_params: Dict[str, Any]
    impact: ModificationImpact
    geometry_diff: Dict[str, float]  # delta_volume, delta_surface_area, delta_bbox
    rebuild_status: str
    error_message: Optional[str] = None
```

### 3.2 核心接口
- **类名：** `AutoIterationEngine`
- **核心方法：**
  - `analyze_impact(current_tree: Dict[str, Any], param_name: str, new_val: float) -> ModificationImpact`
  - `apply_incremental_modification(model_handle: Any, param_name: str, new_val: float) -> IterationDiffResult`

---

## 四、模块四：装配智能规划与约束分析器 (`assembly_planner.py`)

### 4.1 数据结构定义
```python
class MateType(str, Enum):
    COINCIDENT = "coincident"     # 重合配合
    CONCENTRIC = "concentric"     # 同心配合
    DISTANCE = "distance"         # 距离配合
    PARALLEL = "parallel"         # 平行配合

class AssemblyComponent(BaseModel):
    instance_id: str
    part_name: str
    file_path: str
    is_fixed: bool = False
    transform_matrix: Optional[List[float]] = None

class AssemblyMate(BaseModel):
    mate_id: str
    mate_type: MateType
    component_a: str
    reference_a: str              # 引用特征/面名称
    component_b: str
    reference_b: str
    parameter_value: Optional[float] = None

class AssemblyPlan(BaseModel):
    assembly_name: str
    components: List[AssemblyComponent]
    mates: List[AssemblyMate]
    assembly_sequence: List[str]
    has_conflicts: bool = False
    conflict_details: List[str] = Field(default_factory=list)
```

### 4.2 核心接口
- **类名：** `AssemblyPlanner`
- **核心方法：**
  - `plan_assembly(parts: List[Dict[str, Any]], design_constraints: List[Dict[str, Any]]) -> AssemblyPlan`
  - `detect_mate_conflicts(mates: List[AssemblyMate]) -> List[str]`

---

## 五、模块五：多维综合质量评价引擎 (`cad_quality_inspector.py`)

### 5.1 评分雷达与报告模型
```python
class QualityCategoryScore(BaseModel):
    score: float                  # 0.0 ~ 100.0
    weight: float
    passed_checks: List[str]
    warnings: List[str]

class ComprehensiveQualityReport(BaseModel):
    model_name: str
    overall_quality_score: float  # 0.0 ~ 100.0
    is_acceptable: bool           # overall >= 80.0
    geometry_score: QualityCategoryScore
    topology_score: QualityCategoryScore
    stability_score: QualityCategoryScore
    manufacturing_score: QualityCategoryScore
    actionable_recommendations: List[str]
```

### 5.2 核心接口
- **类名：** `CadQualityInspector`
- **核心方法：**
  - `inspect_model_quality(measured_data: Dict[str, Any], theoretical_spec: Optional[Dict[str, Any]] = None) -> ComprehensiveQualityReport`
  - `verify_point_sampling(feature_positions: Dict[str, List[float]], expected_positions: Dict[str, List[float]]) -> QualityCategoryScore`

---

## 六、高级协调器统一入口 (`advanced_ai_cad_coordinator.py`)

提供 `AdvancedAicadCoordinator` 类，提供全局单例或工厂实例，聚合五大模块能力，对外输出干净的 API 与 MCP 统一适配。
