# Server setup guide

一台 Linux 服务器的网络、CLI agent、飞书连接与运维定时任务的脱敏部署手册。
现场基线：2026-10-26；不包含业务项目清单、业务数据、账号、订阅 URL、Cookie 或密钥。

## 从哪里开始

1. 阅读 [部署顺序](docs/bootstrap.md)，确认网卡、DNS、系统用户、SSH 恢复通道。
2. 配置 [Mihomo 网络](docs/network.md) 和 [Shell 工具](docs/shell.md)。
3. 配置 [Tailscale](docs/tailscale.md)、[Claude/Codex 与飞书](docs/agents-and-lark.md)。
4. 按 [定时任务清单](docs/timers.md) 安装需要的任务。
5. 阅读 [第二跳监测](docs/webshare-watch.md)，填写私有参数后再启用自动停止。
6. 对照 [验收与排错](docs/verification.md) 检查。
7. Mac全局约定归档和服务器规则的区别见 [全局记忆与交接](docs/global-memory.md)。
8. 仅第二跳切换/直连超时问题参见 [故障原因、修复和证据](docs/incidents/2026-10-25-webshare-only-timeout.md)。

## 当前状态与边界

- 已运行：服务器 Mihomo 仅第二跳（业务 TCP 经 Webshare，不经机场；系统维护例外保留）、TUN/DNS、系统恢复控制、Tailscale 设备互联、两个 CLI 的飞书 bridge、运维 timers。
- 本仓库新增：每 30 秒检查 Webshare，首次故障停止当前 Claude CLI 进程树，附分段诊断私聊通知；故障期间 AppArmor 阻止已知安装路径启动，常驻 guard 持续清理 Claude；检测恢复时私聊通知并允许新任务，旧任务不自动重启。
- 现场四模式扩展已启用仅第二跳；历史三档与仅第二跳分别做过现场验证。仓库模板是脱敏参考，文件名中的 DRAFT 不代表当前生产状态；不能直接复制参数后宣称部署成功。
- `templates/` 是配置参考，含 `serveruser`、`REPLACE_*` 与文档示例 IP。需替换后才可部署。
- 本机验证与离线测试已做，**尚未在全新服务器端到端重建**，不是不分环境的一键安装器。
- TUN 停止/回滚期间可能恢复系统直连；本仓库的轮询监测不是网络 kill switch。

## 目录

| 路径 | 用途 |
|---|---|
| `docs/` | 部署、架构、维护、排错及当前已验证状态 |
| `scripts/claude_webshare_watch.py` | 新增第二跳监测的实际源代码 |
| `tests/test_watch.py` | 监测状态机、路由判定、PID 身份及安全终止测试 |
| `templates/mihomo/` | 当前扩展脱敏样本、四模式草稿、生成与发布工具 |
| `templates/systemd/` | 系统/用户服务与 timer 样本 |
| `templates/automation/` | 日常检测/更新任务的脱敏脚本 |
| `templates/agents/` | 全局记忆/项目交接约定的脱敏样本 |
| `AGENTS.md` | 本项目唯一交接正文；`CLAUDE.md` 仅引用 |

## 本地检查

```bash
python3 -m unittest discover -s tests -v
node --check templates/mihomo/webshare-dns.current.example.js
node --check templates/mihomo/webshare-dns.four-modes.DRAFT.js
bash -n templates/bashrc-infrastructure.sh
```

安装 Python 依赖：`sudo apt-get install python3-yaml`。监测进程需要 Linux pidfd 支持。

## 凭据与公开仓库

真实配置放仓库外：例如 `/etc/claude-webshare-watch/config.json`（root、0600）。
不要上传原始 bridge profile、CLI auth 文件、环境 JSON、抓包、订阅或生产 YAML。
提交前执行 Gitleaks 文件及 Git 历史扫描，再检查账号标识和非示例公网 IP。

飞书留档采用 Codex profile、用户身份，目录 `我的文档库/server-setup-guide`。
公开仓库不保存私人知识库 URL；本机 `.feishu-links.json`（已忽略）记录实际链接。
