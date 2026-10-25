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
