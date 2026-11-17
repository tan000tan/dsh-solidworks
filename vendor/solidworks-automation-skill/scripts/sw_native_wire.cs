using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Web.Script.Serialization;
using SolidWorks.Interop.sldworks;
using SolidWorks.Interop.swconst;

// 仅由 MCP 的持锁入口调用；没有任意脚本或 COM 方法执行接口。
public static class NativeWireTools {
 public class Sweep { public string name; public double[][] control_points_mm; public double diameter_mm; public double[] color; }
 public class Box { public string name; public double[] bounds_mm,color; }
 public class Spec { public Sweep[] sweeps; public Box[] boxes; }
 public class Request { public int process_id; public string source,action,step_path,output_path,component_name,replacement_path,configuration,feature_name; public string[] body_names; public bool dry_run; public Spec spec; }
 static JavaScriptSerializer json=new JavaScriptSerializer {MaxJsonLength=int.MaxValue};
 [DllImport("ole32.dll")] static extern int GetRunningObjectTable(int reserved,out System.Runtime.InteropServices.ComTypes.IRunningObjectTable table);
 [DllImport("ole32.dll")] static extern int CreateBindCtx(int reserved,out System.Runtime.InteropServices.ComTypes.IBindCtx context);
 static bool Same(string a,string b){return string.Equals(Path.GetFullPath(a),Path.GetFullPath(b),StringComparison.OrdinalIgnoreCase);}
 static ISldWorks Bind(int pid){
  if(pid<=0)throw new Exception("Requested process unavailable");
  System.Runtime.InteropServices.ComTypes.IRunningObjectTable table;System.Runtime.InteropServices.ComTypes.IBindCtx context;
  GetRunningObjectTable(0,out table);CreateBindCtx(0,out context);
  System.Runtime.InteropServices.ComTypes.IEnumMoniker en;table.EnumRunning(out en);var ms=new System.Runtime.InteropServices.ComTypes.IMoniker[1];
  while(en.Next(1,ms,IntPtr.Zero)==0){string name;ms[0].GetDisplayName(context,null,out name);if(name!="SolidWorks_PID_"+pid&&name!="!SolidWorks_PID_"+pid)continue;object obj;table.GetObject(ms[0],out obj);var sw=(ISldWorks)obj;if(sw.GetProcessID()!=pid)throw new Exception("PID mismatch");return sw;}
  // @brief 部分 2026 实例仅注册标准活动对象；只有 PID 与宿主完全一致才允许使用。
  try{var active=(ISldWorks)Marshal.GetActiveObject("SldWorks.Application");if(active.GetProcessID()==pid)return active;}
  catch(COMException){}
  throw new Exception("Requested process unavailable");
 }
 static IModelDoc2 Guard(ISldWorks sw,string path){var d=(IModelDoc2)sw.ActiveDoc;if(d==null||string.IsNullOrEmpty(d.GetPathName())||!Same(d.GetPathName(),path))throw new Exception("Active document target mismatch");return d;}
 static IBody2[] Bodies(IModelDoc2 d){return ((object[])((IPartDoc)d).GetBodies2(-1,false)??new object[0]).Cast<IBody2>().ToArray();}
 static IComponent2[] Components(IModelDoc2 d){return ((object[])((IAssemblyDoc)d).GetComponents(false)??new object[0]).Cast<IComponent2>().ToArray();}
 static double[] Bounds(IBody2 b){return ((double[])b.GetBodyBox()).Select(v=>v*1000).ToArray();}
 static double[] BodyColor(IBody2 b){var c=b.MaterialPropertyValues2 as double[];return c!=null&&c.Length>=3&&c.Take(3).All(v=>v>=0&&v<=1)?c.Take(3).ToArray():null;}
 static object BodyRow(IBody2 b){var m=b.GetMassProperties(1) as double[];return new {name=b.Name,type=b.GetType(),color=BodyColor(b),bounds_mm=Bounds(b),volume_mm3=m==null?0:m[3]*1e9,face_count=b.GetFaceCount()};}
 static object ComponentRow(IComponent2 c){return new{name=c.Name2,path=c.GetPathName(),suppression=c.GetSuppression(),fixed_component=c.IsFixed(),transform=(double[])c.Transform2.ArrayData};}
 static object Document(IModelDoc2 d){return new{title=d.GetTitle(),path=d.GetPathName(),type=d.GetType()};}
 static IEnumerable<IFeature> Features(IModelDoc2 d){for(var f=(IFeature)d.FirstFeature();f!=null;f=(IFeature)f.GetNextFeature())yield return f;}
 static void Paint(IFeature f,string name,double[] rgb){f.Name=name;var faces=f.GetFaces() as object[];if(faces==null||faces.Length==0)throw new Exception("Feature has no faces: "+name);var b=(IBody2)((IFace2)faces[0]).GetBody();b.Name=name;b.MaterialPropertyValues2=new[]{rgb[0],rgb[1],rgb[2],.55,.85,.25,.25,0.0,0.0};var actual=BodyColor(b);if(actual==null||actual.Zip(rgb,(a,c)=>Math.Abs(a-c)).Max()>1.0/255+1e-9)throw new Exception("Body colour readback mismatch");}
 static double Choose(int n,int k){double c=1;for(int i=1;i<=k;i++)c=c*(n+1-i)/i;return c;}
 static double[] Point(double[][] p,double t){int n=p.Length-1;var q=new double[3];for(int i=0;i<=n;i++)for(int a=0;a<3;a++)q[a]+=p[i][a]*Choose(n,i)*Math.Pow(1-t,n-i)*Math.Pow(t,i);return q;}
 static double Length(double[][] p){double len=0;var q=p[0];for(int i=1;i<=2000;i++){var r=Point(p,i/2000.0);len+=Math.Sqrt(q.Zip(r,(a,b)=>(a-b)*(a-b)).Sum());q=r;}return len;}
 static string Equation(double[][] p,int axis){int n=p.Length-1;return string.Join("+",Enumerable.Range(0,n+1).Select(i=>"("+(p[i][axis]*Choose(n,i)).ToString("R",System.Globalization.CultureInfo.InvariantCulture)+")*(1-t)^"+(n-i)+"*t^"+i));}
 static object BuildSweep(IModelDoc2 d,Sweep s){
  d.ClearSelection2(true);var sk=d.SketchManager;sk.Insert3DSketch(true);
  ISketchSegment segment;
  if(s.control_points_mm.Length==2){var a=s.control_points_mm[0];var b=s.control_points_mm[1];segment=(ISketchSegment)sk.CreateLine(a[0]/1000,a[1]/1000,a[2]/1000,b[0]/1000,b[1]/1000,b[2]/1000);}
  else segment=(ISketchSegment)sk.CreateEquationSpline2(Equation(s.control_points_mm,0),Equation(s.control_points_mm,1),Equation(s.control_points_mm,2),"0","1",false,0,0,0,true,true);
  if(segment==null)throw new Exception("Path creation failed: "+s.name);
  sk.Insert3DSketch(true);double measured=segment.GetLength()*1000,expected=Length(s.control_points_mm);
  if(Math.Abs(measured-expected)>Math.Max(.002,expected*.00001))throw new Exception("Path length/unit mismatch");
  var path=(IFeature)d.FeatureByPositionReverse(0);path.Name=s.name+"_PATH";
  d.ClearSelection2(true);var select=((ISelectionMgr)d.SelectionManager).CreateSelectData();select.Mark=4;
  if(!segment.Select4(false,select))throw new Exception("Path selection failed");
  var data=(ISweepFeatureData)d.FeatureManager.CreateDefinition((int)swFeatureNameID_e.swFmSweep);
  data.CircularProfile=true;data.CircularProfileDiameter=s.diameter_mm/1000;data.ThinFeature=false;data.Merge=false;data.TangentPropagation=false;data.AlignWithEndFaces=false;data.TwistControlType=0;data.PathAlignmentType=0;data.StartTangencyType=0;data.EndTangencyType=0;data.AdvancedSmoothing=false;data.MergeSmoothFaces=true;
  var f=(IFeature)d.FeatureManager.CreateFeature(data);if(f==null)throw new Exception("Sweep creation failed: "+s.name);Paint(f,s.name,s.color);
  d.ClearSelection2(true);path.Select2(false,0);d.BlankSketch();d.ClearSelection2(true);
  return new{name=s.name,feature_type=f.GetTypeName2(),path_length_mm=measured,expected_length_mm=expected,diameter_mm=s.diameter_mm};
 }
 static object BuildBox(IModelDoc2 d,Box b){
  d.ClearSelection2(true);var plane=Features(d).First(pf=>pf.GetTypeName2()=="RefPlane");if(!plane.Select2(false,0))throw new Exception("Front plane selection failed");
  var v=b.bounds_mm;var sk=d.SketchManager;sk.InsertSketch(true);sk.AddToDB=true;
  try{sk.CreateLine(v[0]/1000,v[1]/1000,0,v[3]/1000,v[1]/1000,0);sk.CreateLine(v[3]/1000,v[1]/1000,0,v[3]/1000,v[4]/1000,0);sk.CreateLine(v[3]/1000,v[4]/1000,0,v[0]/1000,v[4]/1000,0);sk.CreateLine(v[0]/1000,v[4]/1000,0,v[0]/1000,v[1]/1000,0);}finally{sk.AddToDB=false;}
  sk.InsertSketch(true);var profile=(IFeature)d.FeatureByPositionReverse(0);profile.Name=b.name+"_PROFILE";d.ClearSelection2(true);profile.Select2(false,0);
  var f=d.FeatureManager.FeatureExtrusion3(true,false,false,0,0,(v[5]-v[2])/1000,0,false,false,false,false,0,0,false,false,false,false,false,false,true,3,v[2]/1000,false);
  if(f==null)throw new Exception("Box extrusion failed");Paint(f,b.name,b.color);d.ClearSelection2(true);
  var body=(IBody2)((IFace2)((object[])f.GetFaces())[0]).GetBody();if(Bounds(body).Zip(v,(a,c)=>Math.Abs(a-c)).Max()>.002)throw new Exception("Box plane/units mismatch");
  return new{name=b.name,feature_type=f.GetTypeName2(),bounds_mm=Bounds(body)};
 }
 public static string Run(string input){
  // @brief 只有导入请求保存；未执行保存不能用 saved=false 冒充保存失败。
  var r=json.Deserialize<Request>(input);var sw=Bind(r.process_id);var d=Guard(sw,r.source);var result=new Dictionary<string,object>{{"status","ok"},{"process_id",r.process_id},{"save_requested",r.action=="import"},{"manual_review_required",true}};
  if(r.action=="inspect"){
   if(d.GetType()==1)result["bodies"]=Bodies(d).Select(BodyRow).ToArray();else if(d.GetType()==2)result["components"]=Components(d).Select(ComponentRow).ToArray();
   result["features"]=Features(d).Select(f=>new{name=f.Name,type=f.GetTypeName2()}).ToArray();
  }else if(r.action=="build"){
   if(d.GetType()!=1||d.GetActiveSketch2()!=null)throw new Exception("Part outside sketch mode required");
   if(d.GetUserPreferenceIntegerValue((int)swUserPreferenceIntegerValue_e.swUnitsLinear)!=0)throw new Exception("Millimetre document units required");
   if(Bodies(d).Length!=0)throw new Exception("Empty saved part required; existing geometry is not overwritten");
   if(r.dry_run){result["status"]="ready";}else{
    var rows=new List<object>();foreach(var s in r.spec.sweeps){Guard(sw,r.source);rows.Add(BuildSweep(d,s));}foreach(var b in r.spec.boxes){Guard(sw,r.source);rows.Add(BuildBox(d,b));}
    if(!d.ForceRebuild3(false))throw new Exception("Rebuild failed");
    result["created"]=rows;result["bodies"]=Bodies(d).Select(BodyRow).ToArray();
   }
  }else if(r.action=="import"){
   if(!File.Exists(r.step_path)||File.Exists(r.output_path))throw new Exception("Invalid import paths");
   bool ic=sw.GetUserPreferenceToggle((int)swUserPreferenceToggle_e.swMultiCAD_Enable3DInterconnect),mb=sw.GetUserPreferenceToggle((int)swUserPreferenceToggle_e.swImportMultBodyAsPartData);int map=sw.GetUserPreferenceIntegerValue((int)swUserPreferenceIntegerValue_e.swImportNeutralAssemblyStructureMapping),error=0;
   try{sw.SetUserPreferenceToggle((int)swUserPreferenceToggle_e.swMultiCAD_Enable3DInterconnect,false);sw.SetUserPreferenceToggle((int)swUserPreferenceToggle_e.swImportMultBodyAsPartData,true);sw.SetUserPreferenceIntegerValue((int)swUserPreferenceIntegerValue_e.swImportNeutralAssemblyStructureMapping,2);var data=(IImportStepData)sw.GetImportFileData(r.step_path);data.MapConfigurationData=false;d=(IModelDoc2)sw.LoadFile4(r.step_path,"r",data,ref error);if(d==null||d.GetType()!=1||error!=0||Bodies(d).Length==0)throw new Exception("STEP import failed: "+error);}
   finally{sw.SetUserPreferenceToggle((int)swUserPreferenceToggle_e.swMultiCAD_Enable3DInterconnect,ic);sw.SetUserPreferenceToggle((int)swUserPreferenceToggle_e.swImportMultBodyAsPartData,mb);sw.SetUserPreferenceIntegerValue((int)swUserPreferenceIntegerValue_e.swImportNeutralAssemblyStructureMapping,map);}
   if((IModelDoc2)sw.ActiveDoc!=d)throw new Exception("Active import changed");
   int warn=0;if(!d.Extension.SaveAs(r.output_path,0,1,null,ref error,ref warn)||error!=0||!Same(d.GetPathName(),r.output_path))throw new Exception("STEP save failed: "+error);
   result["saved"]=true;result["warnings"]=warn;result["bodies"]=Bodies(d).Select(BodyRow).ToArray();
  }else if(r.action=="exclude"){
   if(d.GetType()!=1||Features(d).Any(pf=>pf.Name==r.feature_name))throw new Exception("Invalid exclusion target");var all=Bodies(d);var selected=r.body_names.Select(n=>all.Single(b=>b.Name==n)).ToArray();if(selected.Length>=all.Length)throw new Exception("Cannot exclude every body");
   d.ClearSelection2(true);foreach(var b in selected)if(!b.Select2(true,null))throw new Exception("Body selection failed");
   var f=(IFeature)d.FeatureManager.InsertDeleteBody2(false);if(f==null)throw new Exception("Body exclusion failed");f.Name=r.feature_name;d.ClearSelection2(true);d.ForceRebuild3(false);
   if(Bodies(d).Length!=all.Length-selected.Length)throw new Exception("Body exclusion count mismatch");result["excluded"]=selected.Select(b=>b.Name).ToArray();result["bodies"]=Bodies(d).Select(BodyRow).ToArray();
  }else if(r.action=="replace"){
   if(d.GetType()!=2)throw new Exception("Assembly required");var before=Components(d);var old=before.Single(c=>c.Name2==r.component_name);if(!old.IsFixed())throw new Exception("Only fixed components supported");var matrix=(double[])old.Transform2.ArrayData;string oldPath=old.GetPathName();
   if(before.Count(c=>Same(c.GetPathName(),oldPath))!=1||before.Any(c=>Same(c.GetPathName(),r.replacement_path)))throw new Exception("Unique source and new replacement required");
   var other=before.Where(c=>c.Name2!=r.component_name).ToDictionary(c=>c.Name2,c=>new{path=c.GetPathName(),transform=(double[])c.Transform2.ArrayData});
   d.ClearSelection2(true);if(!old.Select4(false,null,false)||!((IAssemblyDoc)d).ReplaceComponents2(r.replacement_path,r.configuration,false,1,false))throw new Exception("Component replacement failed");d.ClearSelection2(true);
   var after=Components(d);if(after.Length!=before.Length)throw new Exception("Component count changed");var current=after.Single(c=>Same(c.GetPathName(),r.replacement_path));
   current.Transform2=(MathTransform)((IMathUtility)sw.GetMathUtility()).CreateTransform(matrix);
   if(!current.IsFixed()){current.Select4(false,null,false);((IAssemblyDoc)d).FixComponent();d.ClearSelection2(true);}
   if(!d.ForceRebuild3(false))throw new Exception("Rebuild failed");
   if(((double[])current.Transform2.ArrayData).Zip(matrix,(a,b)=>Math.Abs(a-b)).Max()>1e-10)throw new Exception("Replacement transform mismatch");
   foreach(var c in after.Where(c=>c.Name2!=current.Name2)){var b=other[c.Name2];if(!Same(c.GetPathName(),b.path)||((double[])c.Transform2.ArrayData).Zip(b.transform,(a,z)=>Math.Abs(a-z)).Max()>1e-10)throw new Exception("Unrelated component changed");}
   result["components"]=after.Select(ComponentRow).ToArray();result["transform_preserved"]=true;
  }else throw new Exception("Unsupported operation");
  if(r.action!="import")Guard(sw,r.source);result["document"]=Document(d);return json.Serialize(result);
 }
}
