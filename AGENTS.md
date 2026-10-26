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
- checkws复用“本地代理+出口IPv4精确匹配”，另核对运行模式和Webshare规则；主检测建连8秒；现场probe_timeout=20秒，默认总超时仍由配置决定。
- 首次故障停止当前Claude进程树并启用AppArmor门禁，持续失败期间保持门禁并清理新进程；检测成功才解除，不自动重启旧任务。
- pidfd/启动时间保护防止PID复用误杀；不通过命令行全文搜索Claude。
- 此处原为三档运行基线；现服务器仅第二跳的现场状态见当前进度，手机仍三档。
- 新仓库公开，所有内容发布前脱敏和秘密扫描；私有飞书链接放本机忽略文件 `.feishu-links.json`。

## 当前进度

- 已完成基础文档、脱敏模板和监测源码。
- watcher 已安装启用，现场出口检测通过；目标私聊故障及恢复通知已用隔离状态演练验证，持续正常不重复通知。
- 自动化测试13项通过，真实kill仅针对测试sleep进程；生产未做断网注入。
- GitHub公开仓库已创建并推送；飞书项目概览和开发记录已创建，回查确认均在目标项目节点下。
- GitHub账号自有仓库已复查，无私有仓库；唯一原私有库经历史凭据扫描后按授权公开。
- 最终文档与源码已进行秘密扫描；现场安装源码hash与仓库一致。
- 新机器完整重建未验证；独立账号隐藏Clash方案未实施；四模式扩展现场状态以当前进度为准。

## 已完成：仅第二跳修复（2026-10-25 纽约时间；北京时间2026-10-26）

服务器正式运行仅第二跳，业务TCP使用Webshare官方网关DIRECT拨号，不经机场；手机仍三档。旧IP端口从TX直连超时，官方域名的系统DNS与两家DoH结果不一致；改用经双方加密DNS核实、独立认证/出口测试通过的官方网关，出口IP保持原值。JS、watcher端点与checkws显示文案已对齐。

当前active SHA256：688f82d802c2ced50a2573d6ace88f9186ea5596add52fce2838397ca8bf196b。用户第二出口新SSH成功；配置/内核/实际出口/Google/飞书TLS/Codex只读探针/watcher check通过；已原skill --accept保留，双回滚timer/service inactive。飞书bridge 21:24:04 EDT重新连接；用户已确认私聊正常回复，日志21:30:40 EDT完成、21:30:45发送。未重启服务器。

完整脱敏复盘见 [docs/incidents/2026-10-25-webshare-only-timeout.md](docs/incidents/2026-10-25-webshare-only-timeout.md)；实际端点、私有备份及恢复包装见服务器私有配置目录的 AGENTS.md；配置目录不是Git项目；本仓库监测源码仅将curl建连上限3改8秒，公开模板账号和密码字段已统一占位符；完整13项单元测试本次通过，源码与已安装副本一致。历史“仍三档/未publish”的进度已过时。

## 2026-10-26：事件复盘与仓库同步

已新增 docs/incidents/2026-10-25-webshare-only-timeout.md，明确TCP建连失败的证据、无法确定具体阻断方、官方接入网关的修复、独立DNS异常与3秒误判，区分历史现场验证及本次检查。README和网络文档的过时三档/未启用描述已修订。同步本轮上次遗留的监测3→8秒变更及说明，保留原门禁/出口判定逻辑。公开模板账号和密码字段已统一为占位符，增加现场真实参数精确匹配检查；历史清理和凭据轮换需单独处理。本次重新运行13项unittest、两份JS语法、Shell语法、git diff --check均通过；历史抓包/用户SSH/私聊证据未在本轮重做。CLAUDE.md仍只引用AGENTS.md；不将私密链接、账号、端点、配置或抓包加入Git。

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

- 2026-10-26（纽约时间）：新增仅第二跳超时事件复盘，区分直接故障位置与未证实原因，补齐修复、验收、维护说明及GitHub/本项目飞书开发记录同步。

- 2026-10-26：新增首次故障分段诊断（第一跳独立探测、已核对路由的Webshare SOCKS/认证/目标连接/TLS/HTTP/出口），双站点重测、18秒硬超时，服务总超时90秒。13项测试及现场只读诊断通过；不改变停任务与恢复逻辑。

- 2026-10-26：补记恢复通知现场演练：真实检测正常、服务active；隔离故障/恢复的两条测试私聊消息成功，持续正常不重复通知；未修改生产门禁或停止真实任务。

- 2026-10-26：恢复成功时新增当前飞书私聊通知；通知按事件顺序持久排队、发送失败重试，持续健康不重复通知，首次启动健康不通知。8项测试通过；旧任务不自动重启。

- 2026-10-25：按用户修订改为故障期间持续拦截；新增AppArmor启动门禁和常驻guard，7项测试及隔离内核门禁/恢复测试（含实际Claude二进制副本）通过，现场已启用，Webshare实测健康。

- 2026-10-25：Codex 创建部署指南、脱敏模板和一次故障一次停止的第二跳监测，现场安装启用；完成公开GitHub推送、飞书归档与位置回查。

- 2026-10-25（纽约时间）：Codex修复仅第二跳直连并通过用户第二出口SSH验收保留；更新当前状态，真实私聊新消息已由用户验收正常；本版本重启仍未验收。

先前修复已记录于 TX Clash 开发记录；2026-10-26 的本项目复盘同步到“我的文档库/server-setup-guide”的既有开发记录。两处实际链接保存在已忽略的 .feishu-links.json，公开仓库不放私人知识库链接。
