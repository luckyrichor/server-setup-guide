# 全局记忆与项目交接

现场实际关系：

```text
~/.codex/AGENTS.md             全局协作、飞书、交接规则
~/.claude/CLAUDE.md            @~/.codex/AGENTS.md，复用同一份正文
~/AGENTS.md                   服务器公共凭据注入约定、bridge验收等待规则
项目/AGENTS.md                本项目唯一交接正文
项目/CLAUDE.md                第一行 @AGENTS.md，只放Claude专属补充
```

templates/agents/ 提供脱敏副本，私人身份与业务例子已概括；它们不是 CLI 厂商内置系统提示词。
不复制 auth、会话历史、远端私有提示词、聊天消息或模型隐藏推理。

## 新机器配置

```bash
mkdir -p ~/.codex ~/.claude
# 先审阅并按自己权限策略修改，不覆盖已有规则。
cp templates/agents/global-AGENTS.example.md ~/.codex/AGENTS.md
printf '@~/.codex/AGENTS.md\n' > ~/.claude/CLAUDE.md
# 将 home-AGENTS.example.md 与现有 ~/AGENTS.md 合并，不能无条件覆盖。
```

项目约定：正文包含项目概述、技术栈、命令、目录、架构、关键决策、进度、下一步、已知问题、待确认、绝对日期更新日志。
阶段结束前更新交接并同步飞书开发记录；日常简单问答不要求建项目。
飞书首次外发确认标题/范围/目录/身份，批准后同项目目录的开发记录可持续追加；署名核实真实提交短哈希。
原记录原则上不改，通过追加更新/更正或新版本保留来源。

共享模型凭据仅记录文件位置和变量名：ARK_API_KEY、TENCENT_API_KEY/TOKENHUB_API_KEY、TENCENT_BASE_URL。
私有目录0700、文件0600，按需对子命令注入，不上传明文或默认注入所有进程。

独立账号+禁止路径列表隔离 Claude 的方案尚未实施；当前 bridge 使用普通服务器账号和高权限 CLI 策略。
不能把一段“不要读取”的提示词当作操作系统访问控制，也不能同时保留任意root能力并保证禁止访问指定文件。


## Mac 全局记忆归档（2026-10-26）

本次“全局记忆”指 Mac 的全局指令正文 `~/.codex/AGENTS.md` 及 Claude 引用 `~/.claude/CLAUDE.md`。它们是用户维护的偏好、协作和交接规则；自动生成的历史摘要、聊天会话和认证文件不属于本次归档。

### 归档文件

| 位置 | 内容与用途 |
|---|---|
| `templates/agents/mac-global-AGENTS.example.md` | Mac 正文的完整脱敏快照，保留33个实际Markdown标题及对应规则，Mac账号路径、助手显示名和业务项目举例概括 |
| `templates/agents/mac-global-CLAUDE.example.md` | 保留原始 `@~/.codex/AGENTS.md` 单行引用，避免双份正文 |
| `templates/agents/mac-global-memory.manifest.json` | 原件和公开副本的字节数、SHA256、来源类型、日期、脱敏范围与标题覆盖数 |
| `private/mac-global-memory/2026-10-26/` | 服务器项目内的原样私有副本和来源清单，已Git忽略；目录0700、文件0600 |

私有原件保留原文；公开快照只做明确的路径/名称脱敏，不删减协作、交接、文档等规则。内容包括新项目根目录确认、中文回复、个人材料位置指引、产品可视化和技术文档、AGENTS/CLAUDE交接、飞书同步/署名/身份、Claude与Codex分工及阶段耗时记录、Android USB/MTP/ADB排查和Mac钥匙串API注入约定。个人材料文件夹正文、真实密钥及手机私有凭据没有随归档复制。

### 完整性与适用范围

- Mac正文原件29366字节，Claude引用原件20字节；服务器私有副本逐文件SHA256与Mac来源相同。
- 公开正文保留全部33个实际Markdown标题（不将代码围栏中的Shell注释计作标题）；逐标题顺序核对。完整hash见manifest，不能期待脱敏副本与原文hash相同。
- 该快照记录Mac环境：`/Users/USERNAME/Project`、macOS钥匙串、Homebrew、Android SDK路径等不是Linux部署路径；采纳前须结合目标机器审阅。
- 本次同步是向本项目归档，不将Mac规则自动安装到服务器 `~/.codex/AGENTS.md`、`~/.claude/CLAUDE.md` 或 `~/AGENTS.md`。服务器原有 `global-AGENTS.example.md` / `home-AGENTS.example.md` 保留，各来源不混写。
- Mac原件及本项目根AGENTS/CLAUDE各司其职，根CLAUDE仍为`@AGENTS.md`；不要把归档快照当作本项目接手进度。

### 以后如何同步

1. 重新读取Mac来源并记录hash，先比较变化；不得根据旧摘要声称已同步最新内容。
2. 在项目私有忽略目录保存原样副本，权限保持0700/0600；公开模板只放已核对的脱敏快照。
3. 更新manifest、完整性记录及根AGENTS进度，检查私有原件不在Git索引中。
4. 通过秘密扫描后提交、推送，核对远端提交，再向本项目既有飞书开发记录追加出处、提交哈希、归档范围和验证结果；旧飞书内容保留。
