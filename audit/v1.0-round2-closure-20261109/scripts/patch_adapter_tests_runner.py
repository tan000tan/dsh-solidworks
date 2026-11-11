import os
import re

adapters_tests = [
    r"D:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin\mcp-server-solidworks-main\adapters\dsh\tests\test_job_store.py",
    r"D:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin\mcp-server-solidworks-main\adapters\dsh\tests\test_orchestrator.py",
    r"D:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin\mcp-server-solidworks-main\adapters\dsh\tests\test_policy.py",
    r"D:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin\mcp-server-solidworks-main\adapters\dsh\tests\test_tool_surface.py",
    r"D:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin\mcp-server-solidworks-main\adapters\claude\tests\test_execution_client.py",
    r"D:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin\mcp-server-solidworks-main\adapters\claude\tests\test_schema_contract.py",
]

main_block = """

if __name__ == "__main__":
    import time
    t0 = time.time()
    funcs = [k for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    failed = 0
    print(f"Running {len(funcs)} tests...")
    for f in funcs:
        try:
            globals()[f]()
            passed += 1
            print(f"  . {f}: PASS")
        except Exception as e:
            failed += 1
            print(f"  F {f}: FAIL - {e}")
    duration = time.time() - t0
    print(f"----------------------------------------------------------------------")
    print(f"Ran {len(funcs)} tests in {duration:.3f}s")
    if failed == 0:
        print("OK")
    else:
        print(f"FAILED (failures={failed})")
        sys.exit(1)
"""

path_header = """import os
import sys
from pathlib import Path

_here = Path(__file__).resolve().parent
_adapter_dir = _here.parent
if str(_adapter_dir) not in sys.path:
    sys.path.insert(0, str(_adapter_dir))
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))
"""

for target in adapters_tests:
    with open(target, "r", encoding="utf-8") as fp:
        code = fp.read()
    
    # 注入路径头
    if "_adapter_dir" not in code:
        code = path_header + "\n" + code
        
    # 注入 main_block
    if '__name__ == "__main__"' not in code:
        code = code + main_block
        
    with open(target, "w", encoding="utf-8") as fp:
        fp.write(code)

print("Adapter tests successfully patched with path resolution and runner!")
