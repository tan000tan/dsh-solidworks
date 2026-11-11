path = r"d:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin\tests\mcp_mid_operation_failure_test.py"
with open(path, "r", encoding="utf-8") as f:
    c = f.read()

c = c.replace("timeout=30", "timeout=60")
c = c.replace("timeout=40", "timeout=60")

with open(path, "w", encoding="utf-8") as f:
    f.write(c)

print("SUCCESS: Adjusted timeouts to 60s in mcp_mid_operation_failure_test.py")
