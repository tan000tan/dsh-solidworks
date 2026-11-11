import json
import time
import os

delivery_dir = r"<PROJECT_ROOT>\v0.3.0-phase1-6-delivery"
evidence_raw = os.path.join(delivery_dir, "evidence_raw")
a_audit = os.path.join(evidence_raw, "A-Audit")
os.makedirs(a_audit, exist_ok=True)

self_check = {
    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    "git_branch": "feat/v0.3.0-phase1-6",
    "base_commit": "9cd64db",
    "questions": [
        {"id": 1, "q": "我是否理解本任务的目标是工程交付而非审计报告？", "a": "是。目标是完成 v0.3.0 候选版本工程开发、重构、安装产品化、实机验证与证据打包，绝不以纸面报告代替代码和构建。", "confirmed": True},
        {"id": 2, "q": "我是否理解最终用户是普通 DSH 用户，不能假设其具备开发环境？", "a": "是。最终用户仅需安装 DSH 插件并具备正版 SolidWorks，无需手动配置 Python/pip/Node/pnpm/虚拟环境/COM注册。", "confirmed": True},
        {"id": 3, "q": "我是否核实了当前工作目录、Git 状态、分支和 upstream？", "a": "是。工作目录 D:\\Agent工作区\\DeepSeek Harness工作区\\dsh-solidworks-plugin，基于 v0.2.0 (9cd64db) 创建 feat/v0.3.0-phase1-6 分支。", "confirmed": True},
        {"id": 4, "q": "我是否已建立当前状态的完整备份/快照，并验证快照可用？", "a": "是。Git baseline 已锁定在 9cd64db (v0.2.0)，所有历史验收归档保留在 audit/、audit_round2_final/ 及项目备份/ 中。", "confirmed": True},
        {"id": 5, "q": "我是否确认了绝对不能 touch 的文件和目录清单？", "a": "是。严格不 touch：audit_round2_final/、audit/、项目备份/、已发布的 v0.2.0 tag/commit、外部用户进程及工作区外非授权文件。", "confirmed": True},
        {"id": 6, "q": "我是否理解六个阶段的先后依赖关系？", "a": "是。严格遵守阶段依赖：先1(事实审计)后2(架构隔离)；先3(安装产品化)后4(CAD功能验证)；先5(安全审批)后6(性能体验优化)，阶段6完成并经过交接模拟后才声称Candidate交付。", "confirmed": True},
        {"id": 7, "q": "我是否理解“先验证再下结论”的原则？", "a": "是。每一个断言必须具备真实命令执行输出、日志和时间戳，严禁使用推测、假设或无依据断言。", "confirmed": True},
        {"id": 8, "q": "我是否知道在执行任何 T4（真实 CAD 写入）测试前，必须获得明确授权并使用安全的测试文件？", "a": "是。所有 T4 写入测试必须在隔离的临时目录进行，严禁覆盖、修改或触碰用户真实 CAD 工程文件。", "confirmed": True},
        {"id": 9, "q": "我是否知道不能终止非本次任务创建的外部进程？", "a": "是。仅可管理本次任务启动的子进程/Worker，严禁无故杀死外部用户打开的 SolidWorks 或其他应用进程。", "confirmed": True},
        {"id": 10, "q": "我是否知道不能通过降低断言或跳过测试来“消除”FAIL？", "a": "是。发现缺陷必须定位根因并修复实现，严禁降低测试标准、注释断言或标记 skip 来作弊。", "confirmed": True},
        {"id": 11, "q": "我是否理解阶段 7、阶段 8 不在本次执行范围内，不应提前执行发布、打 tag 或 push？", "a": "是。阶段7(外部洁净室验证)与阶段8(正式打tag/push/发布/提交市场)超出范围，本次严格止步于 v0.3.0 RC 交付物生成。", "confirmed": True},
        {"id": 12, "q": "我是否准备好了结构化证据收集机制？", "a": "是。已建立 v0.3.0-phase1-6-delivery/evidence_raw/ 及其六大分类子目录 (A-Audit 到 F-Performance)。", "confirmed": True},
        {"id": 13, "q": "我是否理解交付物只有三个文件，且必须位于根目录的指定子目录中？", "a": "是。交付物严格限制为 v0.3.0-phase1-6-delivery/ 下的 final-report.md, evidence.zip, evidence-manifest.md 三个文件。", "confirmed": True},
        {"id": 14, "q": "我是否准备好在每个阶段完成后进行阶段门禁自检？", "a": "是。每个阶段结束前必须执行该阶段门禁自检清单并记录原始日志。", "confirmed": True},
        {"id": 15, "q": "我是否理解所有测试必须记录真实用时，不能写 0.000s？", "a": "是。必须捕获真实高精度 wall-clock 执行时间并记录在测试输出和日志中。", "confirmed": True},
        {"id": 16, "q": "我是否理解如果遇到无法独立解决的障碍，应及时向用户报告而非绕过或猜测？", "a": "是。遇不可逆风险或关键分支决策第一时间上报，不隐瞒、不盲猜。", "confirmed": True}
    ]
}

out_path = os.path.join(a_audit, "pre_execution_self_check.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(self_check, f, indent=2, ensure_ascii=False)

print(f"Pre-execution self-check saved to: {out_path}")
