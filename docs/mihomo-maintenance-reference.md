# TX 维护流程与边界

记录基线：2026-10-04，Mihomo v1.19.31。这不是实时状态，也不证明未来版本兼容。执行前读实际脚本、单元与状态。用户补充的示例经过核对后才采纳。

## 检查现状

```bash
sudo /usr/local/libexec/mihomo-tx-control status
systemctl is-active mihomo-tx-candidate.service mihomo.service
systemctl show mihomo-tx-candidate.service -p MainPID
systemctl list-timers --all 'mihomo-tx*' 'tx-config-update*'
resolvectl dns eth0
/usr/local/bin/mihomo -v
```

不输出完整源文件。当前生成器固定 eth0、回程保护 TCP 22/80/443、路由表 20220 和 mihomo 的 19000–19010 策略规则；发生变化必须复核，不能由本 skill 自动扩展或删除未知规则。

## 修改 JS

在编辑前备份，备份文件也含凭据，目录 0700、文件 0600。只修改请求的字段。`node --check` 没输出且退出码 0 表示语法检查通过；这是语法验证，不是域名有效性、账号连通性或分流验证。失败日志可能包含代码行，展示前删去凭据。

```bash
node --check /home/serveruser/.config/mihomo/tx/webshare-dns.js
sudo bash /home/serveruser/.codex/skills/tx-mihomo-config-publish/scripts/tx-apply-config.sh --check
```

源文件应 owner serveruser:serveruser、0600。清空两份两跳名单保留 `[]` 即只使用基础分流；原 Webshare 节点可能仍存在但不被名单规则使用。默认不会因第二跳不可用而自动切第一跳。

## 上传新订阅（Mac）

```bash
scp '/Users/LOCAL_USER/Downloads/新的机场配置.yaml' tx:/home/serveruser/.config/mihomo/tx/base.upload.yaml
ssh tx 'chmod 600 /home/serveruser/.config/mihomo/tx/base.upload.yaml'
```

同名上传会覆盖上传暂存文件，不会自动更新 base 或正式配置。禁止直接把订阅 URL、Base64、单独节点清单或已扩展 active YAML 当成原订阅。节点数/协议与旧订阅有差异时，报告可见差异并调查来源，不编造筛选原因。

## 准备新订阅的稳定回滚配置（TX）

以下命令只创建和检查副本，不安装。输出路径必须尚不存在；重复执行应先检查旧暂存副本的归属与用途，再换新名称。

```bash
python3 /home/serveruser/.codex/skills/tx-mihomo-config-publish/scripts/check-base.py \
  /home/serveruser/.config/mihomo/tx/base.upload.yaml \
  --js /home/serveruser/.config/mihomo/tx/webshare-dns.js \
  --stable-out /home/serveruser/.config/mihomo/tx/stable.upload.yaml
/usr/local/bin/mihomo -t -d /home/serveruser/.config/mihomo \
  -f /home/serveruser/.config/mihomo/tx/stable.upload.yaml
```

校验器遇错误返回非零，支持 proxy-providers 提供节点；四个规则集是当前 JS 的依赖。程序不核实外部下载和账号有效性，`-t` 也不能替代真实出口检查。原始订阅无需 allow-lan/bind-address 预先符合正式监听条件，正式生成器会覆写；但它没有删除所有额外入口，因此原订阅含 listeners、额外代理端口、TLS/unix 控制入口时校验器会拒绝。先保留上传原件，再在暂存副本里清除这些入口并重新检查。稳定副本额外锁定 mixed-port=7890、allow-lan=false、bind-address=127.0.0.1，关闭 TUN/内置 DNS，删额外代理入口、自定义 listeners 与控制接口。不能仅改 allow-lan 就宣称整个配置没有其他公网入口。

由 agent 创建独立目录复制规则缓存/地理数据库（不要复制正在写入的运行状态库，不使用共享符号链接），把稳定副本改成 mixed-port=17890；逐一改 rule-provider 和 proxy-provider 的 path 指向独立副本，避免两个实例共享可写缓存。候选禁用 TUN、DNS、额外监听/API，使用仅 serveruser 权限运行，检查高位端口空闲。若当前 TUN 会捕获测试进程，必须从日志证明机场连接被内核防回环规则正确处理，不能盲目启动嵌套代理。安全条件无法满足则停止并安排受保护的独立验证窗口。

并行实例验证新第一跳节点、下载规则及境外 HTTP 请求；失败不安装新稳定配置。完成后停掉测试实例并确认端口释放。这个过程需要 agent 按实际 provider/cache 格式实施，不提供可能共享缓存的通用一键后台命令。

## 安装源文件并发布

备份原 base、原稳定 YAML 和 JS（如要编辑）到 root 私有备份目录，同时记录哈希与时间。经上述验证后，用同目录临时文件 + rename 安装新 base 与稳定 YAML，owner serveruser:serveruser、0600；逐步失败时恢复已安装的源文件。若 stable 服务正在运行，不得以为替换磁盘文件立即更新了运行实例，先处理当前 stable 状态。

先只校验当前源文件，再按用户授权发布：

```bash
sudo bash /home/serveruser/.codex/skills/tx-mihomo-config-publish/scripts/tx-apply-config.sh --check
sudo bash /home/serveruser/.codex/skills/tx-mihomo-config-publish/scripts/tx-apply-config.sh --publish
```

脚本不是持续订阅更新器。它只应用已保存的源文件；第一次创建 skill 只测试 --check。--publish 的真实发布路径尚未为这个独立封装重做运行验收，首次使用必须保留现场验收与恢复保护，不能把历史控制脚本验收当成此封装的实测。

脚本独立发布锁 `/run/tx-config-publish.lock` 防止另一次同脚本发布；control.lock 用于短文件事务。另一个 agent 手工编辑源文件不受发布锁保护，发布期间禁止并行改同一套源文件。文件替换后 config 与 deployment 是两个原子 rename，整体不是单次文件系统事务；服务已停，版本校验阻止不一致版本启动。若中途失败，不绕过版本保护，读取备份并恢复匹配的一对文件。

`activate` 是正式重新启用入口，支持回滚后 enabled=false 的状态，生成器并不在 activate/restart 内自动调用。此发布封装在当前正式服务健康时应用已生成的配置，用 `activate` 启动；不要求用户手改 enabled。`restart` 用于已经启用的部署，不能当作回滚后的重新启用命令。直接 stop/start 也可能被 stable 状态保护挡住。

如果用户明确要求从 stable/disabled 状态重新启用，先验证正式配置 hash 与 deployment.version、稳定回滚配置和当前源的预期关系，再使用 control activate；当前发布封装主动拒绝从非 active 状态发布，需 agent 按已核对的控制流程处理，不直接改状态绕过。

## 验收、保留和故障

先提示第二出口 SSH；15 分钟无回复则按 SKILL.md 的用户规则由 Mac 新 SSH 验收，并记录证据类型；验证 ifconfig.me/ipinfo.io 的日志规则与两跳出口、api.ipify.org 的第一跳出口、国内站直连。出口可能变化，不能永久固定示例 IP 为唯一合格值。关闭第二跳后名单目标应改走第一跳。凭据更换必须实测新账号，不把候选解析成功当成认证成功。

通过后执行 SKILL.md 中的 发布脚本 --accept（包括 accept、停发布 timer、清理临时 timer 覆盖），再核对 timer/service 与 status。脚本和 activate 各有回滚保护：只 accept 不会停止 `tx-config-update-rollback.timer`。窗口约 20 分钟，实际截止读 timer，不凭操作时间推测。如果回滚已开始则停止把本轮连通结果算作候选验收。

失败可执行：

```bash
sudo /usr/local/libexec/mihomo-tx-control rollback
sudo /usr/local/libexec/mihomo-tx-control status
journalctl -u mihomo-tx-candidate.service -n 60 --no-pager
```

回滚恢复原稳定代理，不是恢复上一份正式 TUN 配置。旧/新订阅均失效时，恢复网络与 DNS 不等于代理可用。phase=failed 或 cleanup_errors 非空需检查残留；不要删保护规则、清空路由表或 nftables 来强行恢复。

新版本首次真实重启另需授权，VNC 与第二出口待命；重启后十分钟内第二出口登录成功、health 正常才执行 `control confirm`。confirm 是启动确认，accept 是激活确认；不用其中一个替代另一个。不要为了使用此 skill 自动重启服务器。

## DNS 验收边界

账号或订阅更新必须确认加密上游可连；修改 DNS 逻辑时用长窗口 PCAP 覆盖 curl、APT、容器等活动，查看目的地及查询名。允许的腾讯云 DNS 查询也需检查是否仅指定内网/维护例外。收到包统计不等于已打印/保存的记录；无历史 PCAP 不能解释历史包内容。IPv6 出口网站返回 IPv4 地址不能证明 IPv6 ingress 被 TUN 接管，应看实际连接目的地址、日志与路由。

skill 安装文件不含凭据。实际源配置、备份、抓包和日志可能敏感，未经用户授权不上传给外部服务或其他 agent。
