# 设备连接与助手访问边界

2026-10-26 用户确认；由 Codex 执行同步。

## 设备与 SSH 连接约定及 Claude 远程访问限制

**设备与 SSH 连接约定**：当前有 Mac、Windows 和服务器三台设备，分别通过 `ssh luomac`、`ssh luowindows` 和 `ssh tx` 连接。执行远程操作前，应先确认目标设备，并核对连接后的主机身份，避免在错误的设备上操作。

**Claude 远程访问限制**：不允许 Claude 直接访问或操作服务器和 Windows，包括通过 `ssh tx`、`ssh luowindows` 或其他连接方式访问这两台设备。需要在服务器或 Windows 上完成的任务，由 Claude 交给 Codex 执行；Codex 负责连接目标设备并执行操作，Claude 负责指导与验收。

## 执行与验收

- 服务器与 Windows 上的操作由 Codex 连接执行，Claude 根据 Codex 返回的改动、命令输出及其他证据指导与验收；验收本身不构成 Claude 直接访问这两台设备的例外。
- 旧规则中“Claude 可以自行完成”“没有 Codex CLI 时由 Claude 完成”等一般性描述，不构成此访问限制的例外；需要用户另行明确改变约定。
- Windows 的已确认连接别名是 `luowindows`；用户早先表述中的 `ssh windows` 指向 Windows 设备限制，不新增或变更 SSH 别名。

## 已核对的活动规则位置

| 设备 | 共享正文 | Claude 引用 |
|---|---|---|
| Mac | `~/.codex/AGENTS.md` | `~/.claude/CLAUDE.md` → `@~/.codex/AGENTS.md` |
| TX | `~/.codex/AGENTS.md` | `~/.claude/CLAUDE.md` → `@~/.codex/AGENTS.md` |
| Windows | `%USERPROFILE%/.codex/AGENTS.md` | `%USERPROFILE%/.claude/CLAUDE.md` → `@~/.codex/AGENTS.md` |

本轮逐台备份后追加约定，二进制回读核对写入内容，确认 Claude 引用未变。自动历史摘要只通过 Mac 指定的记忆更新目录提交更新，不复制认证或会话。

## 仓库归档范围和验证边界

- `templates/agents/global-AGENTS.example.md` 增补已确认约定；新机器使用前应审阅其余历史规则。
- `templates/agents/mac-global-AGENTS.example.md`、对应 manifest 及 `private/mac-global-memory/2026-10-26/` 保留为前次历史快照，没有冒充当前活动全文；当前新增约定以本文为准。
- 本轮为规则文档同步，不修改 SSH 配置、凭据、系统权限、网络监测或 AppArmor，也没有进行真实 Claude 访问拦截测试。指令约定不能当成系统权限强制隔离。
- 新会话应加载最新规则；已有 Claude 会话是否重新加载未验证。
