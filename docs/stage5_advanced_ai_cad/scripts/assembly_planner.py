"""
装配智能规划与约束分析引擎 (Assembly Planner)
对应第五阶段子阶段 S5-D：
从零件层扩展至装配体层级，规划零部件装配层级、基准零件固定策略、
配合约束关系网 (Coincident/Concentric/Distance/Parallel)，并执行冲突静态检测。
"""
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple
from pydantic import BaseModel, Field


class MateType(str, Enum):
    """配合约束类型"""
    COINCIDENT = "coincident"     # 重合配合
    CONCENTRIC = "concentric"     # 同心配合
    DISTANCE = "distance"         # 距离配合
    PARALLEL = "parallel"         # 平行配合


class AssemblyComponent(BaseModel):
    """装配体零部件节点"""
    instance_id: str
    part_name: str
    is_fixed: bool = False
    description: str = ""


class AssemblyMate(BaseModel):
    """装配体配合约束"""
    mate_id: str
    mate_type: MateType
    comp_a: str
    ref_a: str
    comp_b: str
    ref_b: str
    value: Optional[float] = None
    description: str = ""


class AssemblyPlan(BaseModel):
    """装配体规划结构体"""
    assembly_name: str
    base_component_id: str
    components: List[AssemblyComponent]
    mates: List[AssemblyMate]
    assembly_sequence: List[str]            # 装配时序 (按零部件引入顺序)
    has_conflicts: bool = False
    conflict_details: List[str] = Field(default_factory=list)


class AssemblyPlanner:
    """装配智能规划器"""

    def __init__(self):
        pass

    def plan_assembly(
        self,
        assembly_name: str,
        parts: List[Dict[str, Any]],
        constraints: List[Dict[str, Any]]
    ) -> AssemblyPlan:
        """
        规划装配拓扑图：
        1. 识别并锁定主基准件；
        2. 解析各个配合约束；
        3. 检测配合冲突与过约束；
        4. 生成稳定的装配时序列表。
        """
        components: List[AssemblyComponent] = []
        base_id = ""

        # 1. 寻找基准零件 (优先查找名字带 base / housing / frame / ground 的零件，若无则默认第一个)
        keywords = ["base", "housing", "frame", "body", "plate", "ground"]
        for p in parts:
            p_name = p.get("part_name", "").lower()
            if any(kw in p_name for kw in keywords):
                base_id = p.get("instance_id", f"{p.get('part_name')}_inst")
                break
        if not base_id and parts:
            base_id = parts[0].get("instance_id", f"{parts[0].get('part_name')}_inst")

        for idx, p in enumerate(parts):
            p_name = p.get("part_name", f"part_{idx+1}")
            inst_id = p.get("instance_id", f"{p_name}_inst")
            is_base = (inst_id == base_id)

            components.append(AssemblyComponent(
                instance_id=inst_id,
                part_name=p_name,
                is_fixed=is_base,
                description=f"装配零部件: {p_name}"
            ))

        # 2. 构建配合列表
        mates: List[AssemblyMate] = []
        for idx, c in enumerate(constraints):
            m_type_str = c.get("mate_type", "coincident").lower()
            m_type = MateType(m_type_str)
            mates.append(AssemblyMate(
                mate_id=c.get("mate_id", f"mate_{idx+1}"),
                mate_type=m_type,
                comp_a=c.get("comp_a"),
                ref_a=c.get("ref_a", "face_1"),
                comp_b=c.get("comp_b"),
                ref_b=c.get("ref_b", "face_2"),
                value=c.get("value"),
                description=c.get("description", f"{m_type_str} 配合")
            ))

        # 3. 静态冲突检测 (同一组几何面重复冲突配合)
        conflicts = self._detect_conflicts(mates)

        # 4. 生成装配引入顺序 (基准件优先引入，然后由配合关系拓扑铺展)
        seq = self._generate_assembly_sequence(base_id, components, mates)

        return AssemblyPlan(
            assembly_name=assembly_name,
            base_component_id=base_id,
            components=components,
            mates=mates,
            assembly_sequence=seq,
            has_conflicts=len(conflicts) > 0,
            conflict_details=conflicts
        )

    def _detect_conflicts(self, mates: List[AssemblyMate]) -> List[str]:
        """检测过约束或互斥冲突配合"""
        conflicts = []
        # 检测同一对零件之间是否存在相冲突的配合约束 (如同时指定同心又指定距离矛盾)
        pair_mates: Dict[Tuple[str, str], List[AssemblyMate]] = {}

        for m in mates:
            pair = tuple(sorted([m.comp_a, m.comp_b]))
            if pair not in pair_mates:
                pair_mates[pair] = []
            pair_mates[pair].append(m)

        for pair, m_list in pair_mates.items():
            types = [m.mate_type for m in m_list]
            # 若同一对零件在相同几何引用面上存在多个距离配合且值不相等
            dist_mates = [m for m in m_list if m.mate_type == MateType.DISTANCE]
            if len(dist_mates) >= 2:
                refs = [(m.ref_a, m.ref_b, m.value) for m in dist_mates]
                if refs[0][0] == refs[1][0] and refs[0][1] == refs[1][1] and refs[0][2] != refs[1][2]:
                    conflicts.append(
                        f"零部件 [{pair[0]}] 与 [{pair[1]}] 存在矛盾的距离配合: {refs[0][2]} != {refs[1][2]}"
                    )

        return conflicts

    def _generate_assembly_sequence(
        self,
        base_id: str,
        components: List[AssemblyComponent],
        mates: List[AssemblyMate]
    ) -> List[str]:
        """以基准件为根，按配合树逐层引入零部件"""
        sequence = [base_id]
        remaining = [c.instance_id for c in components if c.instance_id != base_id]

        while remaining:
            added = False
            for cand in list(remaining):
                # 检查该候选件是否与已在装配序列中的零件存在配合
                has_connection = any(
                    (m.comp_a == cand and m.comp_b in sequence) or
                    (m.comp_b == cand and m.comp_a in sequence)
                    for m in mates
                )
                if has_connection:
                    sequence.append(cand)
                    remaining.remove(cand)
                    added = True
                    break

            if not added:
                # 悬浮或未配合零件追加至末尾
                sequence.extend(remaining)
                break

        return sequence
