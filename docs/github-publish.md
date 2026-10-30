# GitHub 发布操作手册（v0.1.0）

本文件只描述**需要授权才能执行**的线上步骤。本轮（2026-10-30/31）已完成的是本地部分：
仓库 `main` 分支、5 个提交、工作树干净、无 remote、无 tag。

目标仓库（已由用户确认）：`https://github.com/tan000tan/dsh-solidworks`

## 0. 发布前最后一次本地校验

```powershell
Set-Location <本仓库根目录>   # 含 package.json 的那一层
$env:DSH_SOLIDWORKS_PYTHON = "<python.exe 完整路径>"   # 只读套件也需要它才能跑 test:host
npm run test:all                                        # 期望 exit 0（110 断言）
node tests/probe-server.mjs                             # 期望 66 tools，无 drift
git status --short                                      # 期望无输出
npm pack                                                # 重新生成 tgz
Get-FileHash .\dsh-solidworks-0.1.0.tgz -Algorithm SHA256
```

当前实测（2026-10-30 收尾）：`test:all` exit 0、110 断言通过、66 工具、
`dsh-solidworks-0.1.0.tgz` **204 文件 / 633,018 B / sha256 `7caeb96c32af718b679807aab54a4258be5a2392ad20ac89b0296d4b1d20c1e4`**。
重新打包后 sha256 会变（`package.json` 里没有固定 mtime），以 `npm pack` 实际输出为准。

## 1. 建仓库并推送（需授权）

```powershell
# 前提：已用有权限的账号登录（gh auth status），并且网络能到达 github.com
gh repo create tan000tan/dsh-solidworks --public --description "Policy-gated SolidWorks CAD plugin for DeepSeek Harness" --source . --remote origin --push
# 或手工：
git remote add origin https://github.com/tan000tan/dsh-solidworks.git
git push -u origin main
```

推送后立刻检查：仓库首页能渲染 `README.md`，`LICENSE` 显示为 AGPL-3.0，`vendor/` 里的 MIT 许可证仍在。

## 2. Tag 与 Release（需授权）

```powershell
git tag -a v0.1.0 -m "v0.1.0 — first public package"
git push origin v0.1.0
gh release create v0.1.0 .\dsh-solidworks-0.1.0.tgz --title "v0.1.0" --notes-file docs/release-notes-v0.1.0.md
```

Release 说明用 `docs/release-notes-v0.1.0.md`（已写好，含实测数字与"写操作未验证"的诚实声明）。
附件只挂 `.tgz`；不要挂 `node_modules` 或整目录压缩包。

## 3. 仓库设置（需授权）

- Topics：`dsh-plugin`（市场收录条件）、`solidworks`、`cad`、`mcp`、`windows`。
- 建议开启：Issues；不强制 Discussions。
- 不要改 README（`awesome-dsh-plugin` 的 README 是自动生成的；**本仓库自己的 README 可以改**）。

## 4. 投稿（需授权）

1. fork `awesome-dsh-plugin/awesome-dsh-plugin`。
2. 新增 `data/plugins/tan000tan__dsh-solidworks.yml`，内容用 `docs/submission/tan000tan__dsh-solidworks.yml`。
3. 先读同目录 2–3 个已有条目，确认 `name` 是 `owner/repo` 还是裸包名、`category` 取哪个合法 id
   （本地 `dshmarket` 客户端不校验词表，见 `docs/market-submission.md` §2 的"三处待核"）。
4. 提 PR，PR 描述里贴：`npm run test:all` 的输出、`probe-server.mjs` 的 66 工具行、tgz 的 sha256。
5. **不要手工改该仓库的 README / plugins.json**（由维护者脚本生成）。

## 5. npm 发布（可选，需授权）

市场既支持 `npm` 字段也支持 `tarball` 字段。若走 npm：

```powershell
npm publish --access public      # package.json 已设 publishConfig.access=public
```

注意：包名 `dsh-solidworks` 在公共 npm 上可能已被占用，发布前先 `npm view dsh-solidworks version` 确认；
被占用就改用 scope（例如 `@tan000tan/dsh-solidworks`），并同步改 `docs/submission/*.yml` 里的 `name`。
插件 `bin` 与 `exports` 不依赖包名，改 scope 不影响代码。

## 6. 回滚

- 包有问题：`npm unpublish dsh-solidworks@0.1.0`（24 小时内）或 `npm deprecate`；GitHub 上删 tag 重建。
- 市场条目有问题：提 PR 撤回，或让维护者标 `deprecated: true`。
- 用户侧：`dsh plugin --profile <p> remove dsh-solidworks`（本插件无 postinstall、不写全局配置，
  卸载后只剩 profile 里一行 `- id: dsh-solidworks` 的 override，无害，见 README §9）。