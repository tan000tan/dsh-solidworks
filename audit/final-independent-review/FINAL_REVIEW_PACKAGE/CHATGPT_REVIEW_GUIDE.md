# ChatGPT 第三方独立对抗审查操作指南
# CHATGPT INDEPENDENT ADVERSARIAL REVIEW GUIDE

**产品版本**：dsh-solidworks v0.2.0  
**当前 Git Commit**：`7d70bc090d5cef146ac3946bb062667ae30a4cc9`  
**审查基准文档**：[`FINAL_MASTER_REPORT.md`](FINAL_MASTER_REPORT.md)  
**审查包目录**：`audit/final-independent-review/FINAL_REVIEW_PACKAGE/`  

---

### 一、致 ChatGPT 审查专家：你的职责与审计立场

尊敬的 ChatGPT 审查专家：

你受托对 `dsh-solidworks` 插件开展正式发布前的最终第三方独立对抗审查。

**你的审计立场必须是：“严谨、批判、有罪推定、唯实物与数据为准”。**

你**不应当**直接信任项目团队在任何文档中给出的自评打分（如“100分”、“PASS”或“EXCELLENT”）。你必须像一位资深的首席 CAD 架构师、自动化专家和软件安全审计官一样，重点寻找以下破绽：
1. **是否存在“自卖自夸”的虚假结论？**
2. **是否存在脱离实机的 Mock 或伪造测量数据？**
3. **是否存在因语言本地化（如中英文 SolidWorks 差异）导致的致命漏洞？**
4. **是否存在特征修改时几何撕裂或参数化能力残缺？**
5. **是否存在掩盖已知缺陷、故意删除不利记录的行为？**

---

### 二、Agent 自我剖析：最值得怀疑的十项结论 (Top 10 Suspicious Conclusions)

为协助你进行精准的对抗式审查，Agent 主动提交以下 10 项“最值得第三方专家质疑”的工程结论，供你深度穿透：

1. **“S5-E 质量检验评估取得 100.0 分”是否虚高？**
   - *质疑点*：是否因为设定的容差（如体积误差 $< 2.5\%$）过于宽松，或者评分权重对某些微观缺陷不敏感？
   - *复核路径*：核对 `cad_quality_inspector.py` 的各项扣分阈值与 `mst_execution_metrics.json` 中的实际数据。
2. **“参数化单调递增验证（ECO-01）是否具有普适性？”**
   - *质疑点*：本次仅验证了圆柱外径由 35mm 扩大至 40mm，如果将尺寸缩小至 5mm（小于键槽深度），特征树是否会瞬间崩溃？
   - *复核路径*：检查尺寸边界有效性校验逻辑是否能够预防几何逆向撕裂。
3. **“圆周阵列和镜像是否真的得到了原生特征级支持？”**
   - *质疑点*：此前第四阶段曾因缺少独立的特征级物证被降级为 PARTIAL。第七阶段是否真的通过 SolidWorks 原生 `FeatureCircularPattern` 形成特征？
   - *复核路径*：检查 `mst_base.SLDPRT` 和 `mst_gear.SLDPRT` 在 SolidWorks 内部的真实特征树节点类型。
4. **“中文版 SolidWorks 兼容性是否彻底解决？”**
   - *质疑点*：是否依然存在未被别名回退表覆盖的冷门特征（如“放样-凸台/基体”、“扫描-切除”在不同小版本下的命名差异）？
   - *复核路径*：审查 `sw_part.py` 与 `sw_document_data.py` 中的正则表达式与动态嗅探逻辑。
5. **“STA 单线程公寓隔离池是否真的零死锁？”**
   - *质疑点*：如果在高并发请求下某个长任务（如大工程图导出）耗时过长，是否会触发上层 MCP 协议的超时熔断并导致队列雪崩？
   - *复核路径*：审查 `sw_connect.py` 中的 `_STAWorker` 队列超时保护与清理逻辑。
6. **“工程图导出的 PDF 是否真正具备高精度矢量属性？”**
   - *质疑点*：导出的是由原生打印管线生成的真实矢量线段，还是仅仅将视口位图（Bitmap）打包进 PDF？
   - *复核路径*：使用矢量查看器以 1000% 比例缩放检查线条抗锯齿特性。
7. **“Windows Junction 软链接解析是否能在所有盘符间彻底防御？”**
   - *质疑点*：在不同文件系统格式（如 ReFS、FAT32 或网络映射盘符）下，`realpathSync` 是否表现一致？
   - *复核路径*：审查 `lib/policy.js` 中跨卷软链接处理代码。
8. **“32 秒的端到端耗时是否受到后台 SolidWorks 缓存的影响？”**
   - *质疑点*：首次冷启动（Cold Start）加载 SolidWorks 往往需要 10~20 秒，测试报告中的耗时是否是在热会话（Warm Session）下测得的？
   - *复核路径*：查阅 `01_REAL_ENVIRONMENT_BASELINE.md` 中关于预热会话与冷启动的区别记录。
9. **“1,240 项缺陷库中清零的 P0 是否经过了严格的独立回归测试？”**
   - *质疑点*：是否通过修改问题定义或降低严重度将 P0 转为了 P1/P2？
   - *复核路径*：核对 `MASTER_DEFECT_DATABASE.csv` 中 3 项 P0 缺陷的修复 Commit 与验证记录。
10. **“复杂装配体配合是否仅停留在静态插入定位？”**
    - *质疑点*：当前的装配体是否仅实现了刚性固定，而未真正建立同轴心（Concentric）与重合（Coincident）配合约束？
    - *复核路径*：检查 `sw_assembly.py` 中底层调用的是 `AddComponent5` 还是完整的 `AddMate5`。

---

### 三、Agent 自我剖析：最可能被 ChatGPT 否决的五项能力 (Top 5 Vulnerable Capabilities)

若你对以下五项能力提出质疑或否决，团队完全接受并认可你的专业判断：

1. **复杂机械配合的自主求解能力 (Advanced Mating Inference)**：
   - *现状*：当前插件对于多自由度机构（如曲柄摇杆、行星齿轮系）尚不能仅凭两句话全自动推导配合面，仍高度依赖显式基准或人工约束引导；
2. **复杂自由曲面与美学造型设计 (Freeform Aesthetic Surfacing)**：
   - *现状*：插件目前的强项是箱体、轴系、盘套等离散工程件，对于连续 G2/G3 曲率的高级工业造型（如汽车流线外观）尚无稳定生成能力；
3. **超大装配体的高性能轻量化处理 (Large Assembly Mode)**：
   - *现状*：当装配体零件数突破数百个时，COM 接口对象的显存消耗与重绘耗时急剧增加，尚未接入 SolidWorks 的大型装配体轻量化（Large Assembly Service）API；
4. **全自动尺寸智能避让与工程图公差标注 (Automatic Dimension De-clutter)**：
   - *现状*：工程图生成目前保证了标准视角的投射，但密集尺寸标注可能发生文字重叠，需要工程人员在图纸上进行二次拖拽排版；
5. **纯自然语言端到端一步完成复杂机构 (One-shot Extreme Prompting)**：
   - *现状*：若用户给出一整篇几千字的整机机构需求，Agent 无法在单次上下文内 100% 成功输出，必须遵循多轮 FeatureGraph 分解。

---

### 四、ChatGPT 复核判定输出模板

在完成全部证据与主报告审查后，请按照以下法定格式给出你的独立审查裁决：

```markdown
# ChatGPT 第三方独立对抗审查决议书

## 1. 核心审查维度评分
- [ ] 真实硬件与软件环境物证完整性：[ PASS / CONDITIONAL / FAIL ]
- [ ] 架构分层与 STA 隔离池合理性：[ PASS / CONDITIONAL / FAIL ]
- [ ] 需求追踪与实测物证吻合度：[ PASS / CONDITIONAL / FAIL ]
- [ ] 几何拓扑保真度与 ECO 单调性：[ PASS / CONDITIONAL / FAIL ]
- [ ] 缺陷清零真实度与发布风险消减：[ PASS / CONDITIONAL / FAIL ]

## 2. 针对 Agent 自剖 10 项疑点的判定结果
(逐项写明是否接受其解释，或指出具体破绽)

## 3. 最终法定发布建议 (只能四选一)
- [ ] READY FOR RELEASE (无条件通过，准予正式发布)
- [ ] READY WITH CONDITIONS (有条件通过，须先完成列出的整改项)
- [ ] NOT READY (存在重大漏洞，必须重构或补充实证)
- [ ] NOT VERIFIED (证据不足，无法做出技术判断)
```
