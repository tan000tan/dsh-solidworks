# 发布包 SHA-256 完整性独立核验报告 (FINAL_SHA256_VERIFICATION)

**核验基线**: 候选发布包 `dsh-solidworks-0.2.0.tgz`  
**核验日期**: 2026年11月9日  
**核验人员**: 独立证据核验小组  

---

## 一、物理文件属性核验

| 属性项 | 核验证实值 |
| :--- | :--- |
| **实际文件物理路径** | `D:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin\dsh-solidworks-0.2.0.tgz` |
| **备用归档一致路径** | `D:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin\dist\dsh-solidworks-0.2.0.tgz`<br>`D:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin\audit\v1.0-round2-closure-20261109\dist\dsh-solidworks-0.2.0.tgz` |
| **文件大小 (字节)** | `1,353,150` 字节 (~1.29 MB) |
| **最后修改时间** | `2026-11-09 16:11:25` |
| **包内成员文件总数** | **452** 个文件 (通过 Python `tarfile` 深度读取遍历证实) |
| **字节码与缓存污染** | **0** 个 `.pyc` / `__pycache__` 成员 (已彻底净化) |

---

## 二、多工具独立计算 SHA-256 摘要与对比

为确保绝对客观、无工具链偏差，采用三种完全独立的工具进行交叉比对：

### 1. 第一次独立计算：Windows 原生 PowerShell (`Get-FileHash`)
- **执行命令**:
  ```powershell
  Get-FileHash -Path "D:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin\dsh-solidworks-0.2.0.tgz" -Algorithm SHA256
  ```
- **原始输出**:
  ```
  Algorithm : SHA256
  Hash      : 12DD5073A2CEC8862B361B31DD3303A7808E8636B9E6066D49408ACBCCAE6FB5
  Path      : D:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin\dsh-solidworks-0.2.0.tgz
  ```

### 2. 第二次独立计算：Windows 原生 `certutil`
- **执行命令**:
  ```powershell
  certutil -hashfile "D:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin\dsh-solidworks-0.2.0.tgz" SHA256
  ```
- **原始输出**:
  ```
  SHA256 哈希:
  12dd5073a2cec8862b361b31dd3303a7808e8636b9e6066d49408acbccae6fb5
  CertUtil: -hashfile 命令成功完成。
  ```

### 3. 第三次独立计算：Python 3.13 原生 `hashlib.sha256()`
- **执行命令**:
  ```python
  import hashlib
  with open(r"D:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin\dsh-solidworks-0.2.0.tgz", "rb") as f:
      print(hashlib.sha256(f.read()).hexdigest())
  ```
- **原始输出**:
  ```
  12dd5073a2cec8862b361b31dd3303a7808e8636b9e6066d49408acbccae6fb5
  ```

### 4. 独立对比判定
三次独立计算的 64 位十六进制散列值**逐位完全一致**：
`12dd5073a2cec8862b361b31dd3303a7808e8636b9e6066d49408acbccae6fb5`

---

## 三、上一轮 40 位摘要错误原因深度复盘

上一轮报告中给出的摘要为：
`e2dd9df6305ab4f0009d5bb61c1e38a989165bba` (长度为 40 个十六进制字符)。

### 根因复查与物理证明：
1. 我们对该文件执行了 **SHA-1** 算法计算：
   ```powershell
   Get-FileHash -Path "dsh-solidworks-0.2.0.tgz" -Algorithm SHA1
   # 输出: E2DD9DF6305AB4F0009D5BB61C1E38A989165BBA
   ```
2. 在 Node.js / NPM 的官方 `npm pack` 输出日志中，其展示的字段为：
   `npm notice shasum: e2dd9df6305ab4f0009d5bb61c1e38a989165bba`
3. **失误机理**: NPM 历史上默认将 160 位 SHA-1 称为 `shasum`。上一轮报告编写者在引用 `npm pack` 的控制台输出时，**误将 npm 输出的 `shasum` (SHA-1) 当作了 SHA-256 写入了交付报告中**。
4. **结论**: 文件本身自始至终未变，40 位字符并非 SHA-256 截断或伪造，而是把标准的 SHA-1 误标注成了 SHA-256。本轮已完全更正为标准的 64 位 SHA-256 摘要。

---

## 四、最终候选发布包确认结论

- **最终候选包物理确认**: `D:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin\dsh-solidworks-0.2.0.tgz`
- **规范标准 64 位 SHA-256**:
  `12dd5073a2cec8862b361b31dd3303a7808e8636b9e6066d49408acbccae6fb5`
- **规范标准 40 位 SHA-1 (NPM shasum)**:
  `e2dd9df6305ab4f0009d5bb61c1e38a989165bba`
- **文件与包体裁决**: **VERIFIED / APPROVED (核验无误，作为正式发布候选包)**。
