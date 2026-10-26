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
系统任务 `claude-webshare-watch.timer` 每30秒触发 root oneshot；`claude-webshare-guard.service` 常驻，故障期间每0.25秒清理进程；通知使用Codex bridge的机器人身份，保留当前绑定环境。

## 关键决定

- 首次故障在拦截/停止并落盘后进行限时分段诊断，将结果附入私聊告警，保存到状态文件 diagnostics；健康判定仍只由原检测负责。
- checkws复用“本地代理+出口IPv4精确匹配”，另核对运行模式和Webshare规则；请求超时10秒。
- 首次故障停止当前Claude进程树并启用AppArmor门禁，持续失败期间保持门禁并清理新进程；检测成功才解除，不自动重启旧任务。
- pidfd/启动时间保护防止PID复用误杀；不通过命令行全文搜索Claude。
- 不启用四模式草稿、不重启Mihomo；运行仍为原三档。
- 新仓库公开，所有内容发布前脱敏和秘密扫描；私有飞书链接放本机忽略文件 `.feishu-links.json`。

## 当前进度

- 已完成基础文档、脱敏模板和监测源码。
- watcher 已安装启用，现场出口检测通过；目标私聊故障及恢复通知已用隔离状态演练验证，持续正常不重复通知。
- 自动化测试13项通过，真实kill仅针对测试sleep进程；生产未做断网注入。
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

AppArmor门禁覆盖npm原生CLI和标准独立安装路径，复制/改名到任意新路径不保证执行前拦截；已识别Claude仍会被常驻guard清理。管理员可卸载策略，不提供对拥有root权限程序的防绕过保证。
轮询不是网络kill switch；一个站点短暂失败也可能触发；复杂自定义规则保守判失败。
子进程已daemonize或交给独立systemd服务后不能仅凭当前进程树追溯。
模板中占位符需替换；源文件仅脱敏参考，新机尚未端到端测试。

## 更新日志

- 2026-10-26：新增首次故障分段诊断（第一跳独立探测、已核对路由的Webshare SOCKS/认证/目标连接/TLS/HTTP/出口），双站点重测、18秒硬超时，服务总超时90秒。13项测试及现场只读诊断通过；不改变停任务与恢复逻辑。

- 2026-10-26：补记恢复通知现场演练：真实检测正常、服务active；隔离故障/恢复的两条测试私聊消息成功，持续正常不重复通知；未修改生产门禁或停止真实任务。

- 2026-10-26：恢复成功时新增当前飞书私聊通知；通知按事件顺序持久排队、发送失败重试，持续健康不重复通知，首次启动健康不通知。8项测试通过；旧任务不自动重启。

- 2026-10-25：按用户修订改为故障期间持续拦截；新增AppArmor启动门禁和常驻guard，7项测试及隔离内核门禁/恢复测试（含实际Claude二进制副本）通过，现场已启用，Webshare实测健康。

- 2026-10-25：Codex 创建部署指南、脱敏模板和一次故障一次停止的第二跳监测，现场安装启用；完成公开GitHub推送、飞书归档与位置回查。
