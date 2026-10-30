"""带显式目标与证据的原生圆截面路径、STEP 导入和组件替换。"""
from __future__ import annotations
import json, math, os, subprocess
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

# @brief 允许最大合法规格通过标准输入传输，同时限制本机子进程的请求体积。
MAX_NATIVE_REQUEST_BYTES = 1024 * 1024

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)

class Sweep(Strict):
    name: str = Field(min_length=1, max_length=100, pattern=r'^[A-Za-z][A-Za-z0-9_]*$')
    control_points_mm: list[tuple[float,float,float]] = Field(min_length=2,max_length=6)
    diameter_mm: float = Field(gt=0,le=100)
    color: tuple[float,float,float] = (.8,.8,.8)
    @model_validator(mode='after')
    def check(self):
        if any(not 0<=v<=1 for v in self.color): raise ValueError('RGB must be within 0..1')
        if any(abs(v)>10000 for p in self.control_points_mm for v in p): raise ValueError('Coordinate exceeds 10 m')
        if math.dist(self.control_points_mm[0],self.control_points_mm[-1])<.001: raise ValueError('Open path required')
        return self

class Box(Strict):
    name: str = Field(min_length=1,max_length=100,pattern=r'^[A-Za-z][A-Za-z0-9_]*$')
    bounds_mm: tuple[float,float,float,float,float,float]
    color: tuple[float,float,float] = (.75,.75,.75)
    @model_validator(mode='after')
    def check(self):
        if any(self.bounds_mm[i+3]<=self.bounds_mm[i] for i in range(3)): raise ValueError('Positive box dimensions required')
        if any(abs(v)>10000 for v in self.bounds_mm): raise ValueError('Coordinate exceeds 10 m')
        if any(not 0<=v<=1 for v in self.color): raise ValueError('RGB must be within 0..1')
        return self

class BuildSpec(Strict):
    sweeps: list[Sweep] = Field(default_factory=list,max_length=64)
    boxes: list[Box] = Field(default_factory=list,max_length=64)
    @model_validator(mode='after')
    def check(self):
        names=[x.name for x in self.sweeps+self.boxes]
        if not names or len(set(names))!=len(names): raise ValueError('Unique feature names required')
        return self

class Target(Strict):
    expected_document_path: str = Field(min_length=1)
    response_format: Literal['json','markdown'] = 'json'

class BuildInput(Target):
    spec_path: str = Field(min_length=1)
    dry_run: bool = True

class ImportInput(Target):
    step_path: str = Field(min_length=1)
    output_path: str = Field(min_length=1)

class ReplaceInput(Target):
    component_name: str = Field(min_length=1)
    replacement_path: str = Field(min_length=1)
    configuration: str = ''

class DeleteInput(Target):
    body_names: list[str] = Field(min_length=1,max_length=256)
    feature_name: str = Field(default='ReviewedBodyExclusion',pattern=r'^[A-Za-z][A-Za-z0-9_]*$')


def invoke_native(sw, target, action, **values):
    """仅由 MCP 在持锁期间调用；不提供任意代码或方法执行。"""
    from scripts.sw_connect import get_com_member as get
    from scripts.cad_installation import discover_installation
    expected=Path(target)
    if not expected.is_absolute(): raise ValueError('Absolute document path required')
    model=get(sw,'ActiveDoc')
    if model is None or os.path.normcase(os.path.abspath(get(model,'GetPathName')))!=os.path.normcase(os.path.abspath(str(expected))):
        raise ValueError('Active document target mismatch')
    install=Path(discover_installation('solidworks')['executable']).parent
    interop=next((p for p in [install/'api/redist',install] if (p/'SolidWorks.Interop.sldworks.dll').is_file()),None)
    if not interop: raise FileNotFoundError('Installed SOLIDWORKS PIA not found')
    payload=dict(process_id=int(get(sw,'GetProcessID')),source=str(expected),action=action,**values)
    request=json.dumps(payload,ensure_ascii=False,allow_nan=False)
    if len(request.encode('utf-8'))>MAX_NATIVE_REQUEST_BYTES: raise ValueError('Native request exceeds 1 MiB')
    proc=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(Path(__file__).with_suffix('.ps1')),'-InteropRoot',str(interop)],input=request,capture_output=True,encoding='utf-8',errors='replace',timeout=240,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if proc.returncode: raise RuntimeError(proc.stderr.strip() or proc.stdout.strip())
    return json.loads(proc.stdout.lstrip('\ufeff'))


def register_tools(mcp, connect, run_locked, response_enum):
    """注册固定操作集，沿用宿主进程绑定与操作锁。"""
    def run(params,action,**values):
        def op():
            sw,_=connect(wait_seconds=1)
            return invoke_native(sw,params.expected_document_path,action,**values)
        return run_locked(op,response_enum(params.response_format))

    @mcp.tool(name='solidworks_inspect_native_geometry',annotations={'readOnlyHint':True,'destructiveHint':False})
    def inspect(params:Target)->str:
        """读取实体名称、包围盒、体积、错误和组件变换，不保存。"""
        return run(params,'inspect')

    @mcp.tool(name='solidworks_build_round_sweeps',annotations={'readOnlyHint':False,'destructiveHint':False})
    def build(params:BuildInput)->str:
        """创建原生方程路径圆截面扫描及矩形拉伸；严格规格，无任意表达式，不保存。"""
        path=Path(params.spec_path)
        if not path.is_absolute(): raise ValueError('Absolute spec path required')
        spec=BuildSpec.model_validate_json(path.read_text(encoding='utf-8-sig'))
        return run(params,'build',dry_run=params.dry_run,spec=spec.model_dump())

    @mcp.tool(name='solidworks_import_step_part',annotations={'readOnlyHint':False,'destructiveHint':False})
    def import_step(params:ImportInput)->str:
        """导入 STEP 为新多实体零件，保存到新文件并恢复导入选项；不改源文件。"""
        src,dst=Path(params.step_path),Path(params.output_path)
        if not src.is_absolute() or not src.is_file() or src.suffix.lower() not in {'.step','.stp'}: raise ValueError('Existing absolute STEP path required')
        if not dst.is_absolute() or dst.exists() or dst.suffix.lower()!='.sldprt' or not dst.parent.is_dir(): raise ValueError('New absolute SLDPRT path in existing directory required')
        return run(params,'import',step_path=str(src),output_path=str(dst))

    @mcp.tool(name='solidworks_replace_component_preserving_transform',annotations={'readOnlyHint':False,'destructiveHint':False})
    def replace(params:ReplaceInput)->str:
        """按精确实例名替换一个固定组件，保留变换并校验其余组件；不保存。"""
        path=Path(params.replacement_path)
        if not path.is_absolute() or not path.is_file() or path.suffix.lower() not in {'.sldprt','.sldasm'}: raise ValueError('Existing absolute native component required')
        return run(params,'replace',component_name=params.component_name,replacement_path=str(path),configuration=params.configuration)

    @mcp.tool(name='solidworks_exclude_reviewed_bodies',annotations={'readOnlyHint':False,'destructiveHint':False})
    def exclude(params:DeleteInput)->str:
        """通过原生删除实体特征排除明确指定的实体，保留可编辑历史，不保存。"""
        if len(set(params.body_names))!=len(params.body_names): raise ValueError('Duplicate body name')
        return run(params,'exclude',body_names=params.body_names,feature_name=params.feature_name)
