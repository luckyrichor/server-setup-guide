# server-setup-guide 交接

## 概述与范围

公开的服务器基础设施部署手册：Mihomo/Clash、Tailscale、Shell函数、网络自检、systemd定时任务、Claude/Codex与飞书bridge、全局记忆。
不记录业务项目列表/数据，不保存真实账号、Cookie、密钥、订阅URL、个人公网IP或飞书身份。

## 技术与快速检查

Python3 + PyYAML，Linux pidfd、curl、systemd；JS扩展由Node执行。依赖 `python3-yaml`。

```bash
python3 -m unittest discover -s tests -v
node --check templates/mihomo/webshare-dns.current.example.js
node --check templates/mihomo/webshare-dns.four-modes.DRAFT.js
bash -n templates/bashrc-infrastructure.sh
```

目录/入口见 README。真实 watcher 配置在仓库外 `/etc/claude-webshare-watch/config.json`；状态 `/var/lib/claude-webshare-watch/state.json`。
系统任务 `claude-webshare-watch.timer` 每30秒触发 root oneshot；通知使用Codex bridge的机器人身份，保留当前绑定环境。

## 关键决定

- checkws复用“本地代理+出口IPv4精确匹配”，另核对运行模式和Webshare规则；请求超时10秒。
- 首次故障只停止当前Claude进程树，持续失败不杀后启动任务；恢复重新布防，不自动重启、不设启动门禁。
- pidfd/启动时间保护防止PID复用误杀；不通过命令行全文搜索Claude。
- 不启用四模式草稿、不重启Mihomo；运行仍为原三档。
- 新仓库公开，所有内容发布前脱敏和秘密扫描；私有飞书链接放本机忽略文件 `.feishu-links.json`。

## 当前进度

- 已完成基础文档、脱敏模板和监测源码。
- watcher 已安装启用，现场出口检测通过；目标私聊通知已验证。
- 自动化测试5项通过，真实kill仅针对测试sleep进程；生产未做断网注入。
- GitHub公开仓库已创建并推送；飞书项目概览和开发记录已创建，回查确认均在目标项目节点下。
- GitHub账号自有仓库已复查，无私有仓库；唯一原私有库经历史凭据扫描后按授权公开。
- 最终文档与源码已进行秘密扫描；现场安装源码hash与仓库一致。
- 新机器完整重建未验证；独立账号隐藏Clash方案未实施；四模式扩展未启用。

## 下一步/维护

1. 更改网络配置后同步 watcher 的 Webshare server/expected_ip，并先执行 --probe-only。
2. 新平台核对网卡、DNS、systemd网络路径及回滚配置，不能直接批量启用模板。
3. 任何后续改动先测试故障状态机，不用生产Claude任务作破坏性验收。
4. 继续更新部署指南并在既有飞书项目目录追加开发记录。

## 飞书位置

已授权目录：我的文档库/server-setup-guide；Codex profile，--as user。
实际目录及文档链接保存在本机 `.feishu-links.json`，不进公开仓库；正文发布注明真实代码版本。

## 已知边界

轮询不是网络kill switch；一个站点短暂失败也可能触发；复杂自定义规则保守判失败。
子进程已daemonize或交给独立systemd服务后不能仅凭当前进程树追溯。
模板中占位符需替换；源文件仅脱敏参考，新机尚未端到端测试。

## 更新日志

- 2026-10-25：Codex 创建部署指南、脱敏模板和一次故障一次停止的第二跳监测，现场安装启用；完成公开GitHub推送、飞书归档与位置回查。
