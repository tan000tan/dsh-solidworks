from pathlib import Path

files = [
    r"d:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin\tests\failure_injection_test.py",
    r"d:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin\tests\mcp_failure_cleanup_e2e_test.py",
    r"d:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin\tests\mcp_mid_operation_failure_test.py"
]

guard_snippet = """        from sw_connect import solidworks_processes
        if not solidworks_processes():
            raise unittest.SkipTest("未检测到运行中的 SolidWorks 进程，跳过实机物理测试以保护待机基线")
"""

for fpath in files:
    p = Path(fpath)
    text = p.read_text(encoding="utf-8")
    if "def setUpClass(cls):" in text and "solidworks_processes" not in text:
        text = text.replace(
            "    def setUpClass(cls):\n",
            "    def setUpClass(cls):\n" + guard_snippet
        )
        p.write_text(text, encoding="utf-8")
        print(f"SUCCESS: Patched setUpClass in {p.name}")
    else:
        print(f"SKIPPED or already patched: {p.name}")
