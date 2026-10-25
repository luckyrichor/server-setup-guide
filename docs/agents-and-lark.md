# Claude / Codex 与飞书 bridge

## 安装与身份

Node 由 NVM 管理；系统服务使用明确的 Node 绝对路径，不依赖交互 shell。
现场 Claude 为 @anthropic-ai/claude-code npm 包内的原生可执行文件；Codex 为 @openai/codex。

```bash
npm install -g @anthropic-ai/claude-code @openai/codex @larksuite/cli lark-channel-bridge
claude --version
codex --version
lark-cli --version
lark-channel-bridge --help
```

登录各 CLI 使用它们各自的交互流程；auth 文件不要提交 Git。Codex 当前模型/推理档是用户偏好，不是部署必需；新机器自行选择可用模型。
官方 Codex CLI 文档：https://learn.chatgpt.com/docs/cli ，配置通常在 ~/.codex/config.toml。
Claude 个人配置 ~/.claude/settings.json；不要把代理密码或 API key 放进公开样本。

## Bridge profile

```bash
lark-channel-bridge profile create --help
lark-channel-bridge profile create claude
lark-channel-bridge profile create codex
lark-channel-bridge start --profile claude --agent claude --workspace "$HOME/project"
lark-channel-bridge start --profile codex --agent codex --workspace "$HOME/project"
```

按实际版本的交互引导注册/选择飞书应用、设置权限与事件订阅，不在命令历史中明文写 App Secret。
不同助手分别使用 claude/codex profile。机器人收消息需应用事件权限、长连接和群访问规则；机器人在群内通常需结构化 @ 才触发。

真实目录 ~/.lark-channel/profiles/PROFILE/ 包含私有配置、会话、日志及 lark-cli 绑定投影，均不提交。
bridge 子进程注入 LARK_CHANNEL、LARK_CHANNEL_HOME、LARK_CHANNEL_PROFILE、LARK_CHANNEL_CONFIG、LARKSUITE_CLI_CONFIG_DIR。
不要 unset 这些变量切回其他本机账号；提示 context not bound 时停止并由用户运行 doctor/preflight 或重启 bridge，不自行读取配置密钥/重新 bind。

## systemd 与运行中追加消息

现场两个用户服务名：lark-channel-bridge.bot.claude.service、lark-channel-bridge.bot.codex.service。
Restart=always；仅保证 bridge 常驻，不表示 CLI 或模型一直运行。
templates 中基础 unit 需改 Node 路径。现场还有部署版本固定的 steering drop-in：

- Claude：独立发布目录，LARK_CLAUDE_STEERING=1。
- Codex：另一发布目录，LARK_CODEX_STEERING=1。

它们依赖本机特定发布产物，不是 npm 安装后一定存在的文件；新服务器必须部署对应源码/发行产物并验证，不能只复制路径。
支持运行中追加消息是否在工具阻塞后立刻交付，还取决于 adapter 处理节点。

Claude 启动方式为 -p、stream-json 输入/输出、--verbose、--permission-mode bypassPermissions，并附加 bridge 提示词文件；已有会话可 --resume。
Codex bridge 当前使用 danger-full-access。两者是现场高权限策略，不是最低权限默认；独立用户/容器隔离方案仅讨论，未实施。

现场 Claude bridge 已移除 http_proxy/https_proxy/all_proxy，依靠 TUN；Codex bridge 仍显式设置本地代理变量。
本地 CLI 及其工具有当前系统账号的能力；模型本身不会自动收到机场节点变更通知。

```bash
systemctl --user status lark-channel-bridge.bot.claude.service
systemctl --user status lark-channel-bridge.bot.codex.service
systemctl --user cat lark-channel-bridge.bot.claude.service
```

日志是 unit 中 StandardOutput/StandardError 指定文件，不一定在 journal 中有完整内容。

## 飞书用户授权与文档

机器人发消息与用户身份写文档不同。用户文档显式 --as user，使用实际助手 profile。
OAuth 只在私聊开展；设备授权链接不要发群。授权不是发布批准。
重要内容首次发布先确认标题、范围、目录、新建层级、身份；Wiki my_library 先列节点、再复用或建目录、最后建文档，完成后回查。
每篇正文注明助手、北京时间、实际仓库版本和 profile。不要把云盘 Drive 文件夹与个人知识库 Wiki 节点混用。
