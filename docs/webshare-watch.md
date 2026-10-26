# Claude 第二跳网络监测

## 授权后的最终语义

用户要求：不论仅 Webshare、全面两跳、名单两跳，都必须确认 Webshare 出口；只走第一跳也算失败。
失败时立即加载 AppArmor 启动门禁、停止当前 Claude CLI 和可识别子进程，并在配置的飞书私聊通知。
持续故障期间不允许新 Claude 任务运行；每轮检测继续清理，常驻 guard 每0.25秒补充清理。
检测成功后解除门禁，并在当前飞书私聊发送一次恢复通知，允许之后的新任务；不自动重启已停止的任务，也不排队重放故障期间被拒绝的请求。

## 检测链路

1. 从私有 Mihomo 配置读取管理密钥，用 localhost API 查看运行 mode、proxies、rules。
2. 核对活动规则存在通向对应 Webshare SOCKS5 的探测路径，不能只看到配置里有一个闲置 Webshare 节点就通过。
3. 与 checkws 一样，强制 HTTP 本地代理请求 https://ifconfig.me/ip，IPv4，连接超时8秒、请求总超时由 probe_timeout 配置（当前现场20秒），无重试。
4. 要求返回有效 IP 且与 expected_ip 完全一致；再检查一次运行模式仍具备 Webshare 路径。
5. 无法确认/超时/认证失败/IP不符/只走第一跳均为失败。

mode=rule、global、direct 均有明确处理；不认识的模式拒绝通过。自定义复杂规则/代理组可能保守判失败，迁移后需补对应支持和测试。
这不是完整 Mihomo 规则模拟器；最终出口实测是关键证据。相同出口服务必须使用稳定 IP，轮换住宅出口应先设计新的验证方式。
服务器目前采用从 Webshare server 取得的固定 expected_ip；更换账号/IP 后必须同步私有 watcher 配置。

## 故障状态机

```text
健康 → 检测失败 → 内核门禁 + 停止当前任务 + 私聊通知
                     ↓
                  持续失败：保持门禁，持续清理新进程，故障/恢复通知失败则重试
                     ↓
                  检测恢复：解除门禁，私聊恢复通知，允许新任务，不重启旧任务
```

### 启动门禁与持续清理

`/etc/apparmor.d/claude-webshare-gate` 是 root 管理的 AppArmor 配置。
监测失败时加载封闭 profile，健康时从内核卸载；策略文件保留，因此标准 AppArmor 开机加载后默认阻止，直到健康检测解除。
覆盖任何前缀下的 `node_modules/@anthropic-ai/claude-code/bin/claude.exe`、`.local/share/claude/versions/*`，以及 `/usr/local/bin/claude`、`/usr/bin/claude`。
通过符号链接启动时，内核按实际二进制路径匹配。升级到相同安装布局仍受保护，不改写 Claude 文件或 bridge。
依据：[Ubuntu AppArmor配置语法](https://manpages.ubuntu.com/manpages/noble/man5/apparmor.d.5.html)。

`claude-webshare-guard.service` 常驻读取健康状态；失败/状态缺失时，每0.25秒清理可识别的 Claude 进程树。
它补充处理非标准路径和门禁加载失败，不能把轮询说成绝对的执行前拦截。
复制并重命名到任意路径、不同CLI实现、容器独立安装等需要另行登记策略；拥有管理员权限的进程仍可改变系统策略。
若门禁操作异常，按失败处理并通知，不宣称门禁已正确加载。

只按进程可执行文件/argv0/comm 识别 Claude，不按任意命令行包含“claude”匹配，避免误杀其他进程。
以 /proc 父子关系记录子进程；pidfd + 启动时间核对防止 PID 复用误杀。SIGKILL 直接终止，未完成工作可能中断。
root oneshot 可检查不同系统账号的 Claude；不停止 bridge、Codex 独立会话、Mihomo 或用户 timers。
独立 Codex 不受影响；若 Codex 是某个 Claude 任务仍关联的子进程，则属于那次任务的停止范围。
已经脱离父进程/成为其他服务的后台任务不能仅凭现存父子关系可靠追溯，需具体服务额外登记。

## 安装

依赖：Linux pidfd、已启用的 AppArmor、apparmor_parser、Python3、PyYAML、curl、lark-cli、可用的 Mihomo API 与正确绑定的 codex profile。

```bash
sudo apt-get install python3-yaml curl apparmor
sudo install -d -m 700 /etc/claude-webshare-watch /var/lib/claude-webshare-watch
sudo install -m 755 scripts/claude_webshare_watch.py /usr/local/libexec/claude-webshare-watch.py
# 按模板私下编辑配置，替换所有占位符。
sudo install -m 600 templates/claude-webshare-watch.config.example.json /etc/claude-webshare-watch/config.json
sudoedit /etc/claude-webshare-watch/config.json
sudo python3 /usr/local/libexec/claude-webshare-watch.py --config /etc/claude-webshare-watch/config.json --probe-only
```

probe-only 不停止进程、不通知、不写故障状态；会创建用于互斥的锁文件和执行真实网络请求。
确认正确后：

```bash
# 先生成持久策略文件（此命令不加载，不影响当前任务）。
sudo python3 - <<'GATE'
import importlib.util
from pathlib import Path
spec = importlib.util.spec_from_file_location('watch', '/usr/local/libexec/claude-webshare-watch.py')
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)
Path('/etc/apparmor.d/claude-webshare-gate').write_text(w.gate_profile())
GATE
sudo install -m 644 templates/systemd/claude-webshare-watch.{service,timer} templates/systemd/claude-webshare-guard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl start claude-webshare-watch.service
sudo systemctl enable --now claude-webshare-watch.timer claude-webshare-guard.service
sudo systemctl status claude-webshare-watch.timer
sudo journalctl -u claude-webshare-watch.service -n 10 --no-pager
```

状态在 /var/lib/claude-webshare-watch/state.json，root 0600；只有健康状态、原因、PID 及通知状态，没有代理账号密码。
通知在 serveruser 对应的普通用户下调用 bridge-bound lark-cli --as bot，不使用用户文档身份，不将 root 凭据或模型环境注入 CLI。
notification_env 只保存 bridge 必需的5个上下文变量；不要从其他 profile 复制密钥或自行 bind。

停用时需同时关闭 timer 和 guard；如门禁已加载，还需卸载策略并移走策略文件以防开机加载。
以下操作会取消网络故障保护，按实际维护需要执行；不会重启已停止任务：

```bash
sudo systemctl disable --now claude-webshare-watch.timer claude-webshare-guard.service
sudo systemctl stop claude-webshare-watch.service
# 仅在内核中存在该策略时运行 -R：
sudo apparmor_parser -K -R /etc/apparmor.d/claude-webshare-gate
sudo mv /etc/apparmor.d/claude-webshare-gate /etc/claude-webshare-watch/gate.disabled
```


## 验证与局限

- 单元测试覆盖规则模式、首跳模式、GLOBAL、持续故障重复停止、恢复解除门禁、门禁失败继续停止、probe-only不改门禁、恢复重新布防、通知重试、PID复用保护。
- 13项单元测试通过；隔离测试用复制的true程序及实际Claude原生二进制验证门禁拒绝启动、卸载后正常启动；加载测试使用与生产相同的NoNewPrivileges/ProtectSystem约束。
- 真实 SIGKILL 只在测试创建的 sleep 子进程验证，没有人为制造生产断网或停止用户真实任务。
- 现场 probe-only 和启用后定时运行均确认 Webshare出口，通知在目标私聊实测成功。
- 30 秒为 timer 周期；检测/调度耗时叠加，不能保证故障瞬间停止。服务不并发运行，繁忙或通知超时会延迟后续轮次。
- ifconfig.me 不可用也会按失败处理，这是用户选择的一次失败即停止策略；没有双站点容错。
- 这个任务不阻断网络，不证明没有 DNS/IPv6/其他域名绕行，也不保证所有 Claude 请求的域名都在两跳名单中。

## 恢复通知

仅在故障转为健康且门禁成功解除时通知；首次启动即健康、持续健康不通知。
故障和恢复事件按时间顺序写入状态文件，兼容旧版 pending_alert；每轮最多发送一条，以免超过服务超时。
发送失败保留队列，下一轮使用同一幂等键重试。若故障通知积压，恢复通知会延后发送。
不自动重启旧任务，不重放被拒绝的任务。8项单元测试覆盖恢复通知、失败重试和持续健康不重复通知。

## 2026-10-26 实测记录（北京时间）

- 手动触发已安装的 `claude-webshare-watch.service`，Result=success、ExecMainStatus=0，实际 Webshare 出口检测正常。
- `claude-webshare-watch.timer` 与 `claude-webshare-guard.service` 均 active。
- 使用临时状态文件模拟故障、恢复、持续正常；替换检测、门禁和进程终止操作，仅复用已安装脚本的真实飞书发送链路。
- 当前私聊中的故障和恢复两条演练消息发送成功，均标明“演练测试，非真实故障”。第三次持续正常检查没有重复发送。
- 本次未切断生产网络、未更改生产门禁或健康状态、未停止真实 Claude 任务。此演练验证状态转换与通知链路，不等同于生产断网验收。
- 8项自动化测试再次通过；旧任务不自动重启的行为保留。

## 首次故障分段诊断（2026-10-26）

故障处理顺序：门禁 → 停止当前进程 → 持久保存故障及待发通知 → 限时诊断 → 将诊断附到私聊告警。
持续同一故障不反复诊断、不重复新报警；下次恢复后再故障重新采集。恢复仍以正式健康检测和解除门禁成功为准。
诊断本身不会切换节点、重启Mihomo、更改规则或提前放行Claude。

1. 读取本机Clash管理API与当前模式；只走第一跳等模式标为“配置/模式问题”，不称为物理断网。
2. 第一跳独立探测：通过Clash命名出站delay API，让当前第一跳访问gstatic测试站。失败时只能判断第一跳测试不通，不能区分服务器到节点、节点自身出站、节点DNS或测试站。
3. 通过本机HTTP代理连接Webshare，使用connections API按源端口确认实际沿同一第一跳、未绕到Webshare链路；未确认则放弃细分，也不发送认证信息。
4. 分别记录Webshare SOCKS响应、用户名密码认证、Webshare到目标（含远端DNS）的TCP连接、TLS、HTTP及出口IP校验。
5. 并行重测ifconfig.me与api.ipify.org，避免只观察单个站点。第二个站点只作为诊断，不改变“一次正式探测失败即拦截”的策略。

告警示例：“第一跳独立探测通过；ifconfig.me：Webshare代理认证失败”“Webshare→目标网站连接失败（包含远端DNS）”“目标网站TLS握手失败”。
主curl返回码也进入失败原因。异常详情只保留固定文案/错误类型/协议状态码，不输出异常原文、账号密码或管理密钥。
完整阶段和累计耗时保存在root私有状态文件的diagnostics字段。

只走第二跳时无第一跳，相关握手分段标为不适用；当前原生分段追踪要求无认证本机HTTP代理、IP形式Webshare地址、可核对的第一跳路径。
不支持的模式/代理类型、管理API不可用、未知路由会明确说明无法定位，不生成虚构结论。
诊断是故障之后的重测；全部通过只说明重测时通了，不能反推此前失败在哪里。

每条分段链路使用8秒总预算、单次socket至多3秒；诊断子进程整体18秒硬超时。服务总超时105秒，以容纳原检测、门禁及通知重试。
诊断可能让首次通知延后至多约18秒，但停止/拦截先执行，常驻guard在诊断期间继续工作。

只读手动诊断（不改状态、不杀进程、不改门禁、不通知）：

```bash
sudo python3 /usr/local/libexec/claude-webshare-watch.py --config /etc/claude-webshare-watch/config.json --diagnose-only
```

验证：13项单元测试通过，包括认证拒绝、SOCKS/目标连接/TLS/HTTP失败、路由未确认、诊断超时、先停止后诊断、脱敏输出及原故障/恢复状态机。
现场只读诊断验证当前第一跳及两个站点的全部阶段正常；没有故意制造生产断网或终止真实Claude任务。


## 2026-10-25 仅第二跳官方入口适配

服务器改用经可信DNS和独立认证核验的Webshare官方Backbone网关；入口IP与出口IP不相同，watcher webshare_server必须匹配入口，expected_ip继续匹配原出口。主检测curl的连接预算包含TCP/TLS；实测3秒会误判正常但稍慢的连接，现为8秒，现场总预算20秒；checkws同步8/20。身份、出口、路由核对和故障门禁逻辑不变。此前独立分段诊断trace的时限未变。13项完整测试通过，最终连续三次现场主检测通过；入口实际值保存在私有配置，不写进公开模板。


## 2026-10-26：瞬时TLS错误复核与仅第二跳诊断

现场发现单次TLS/接收错误可在下一轮恢复；并行测试中也存在一个查询失败而其他查询经同一出口成功，不能据单次失败确定代理整体断开或具体阻断方。经用户明确允许：主探测curl35/56时，同轮最多一次改用fallback_probe_url独立站点复核，预算上限10秒；必须仍确认该站点使用Webshare、响应为有效且匹配的出口，且结束时路由未变。错误出口、模式异常、HTTP失败及备用失败仍为失败；28等其他返回码仍按原策略失败，不将该变更称作全错误自动重试。正常请求不额外探测，不增加多轮容忍。

主探测20秒、连接8秒；加入一次复核后服务总时限105秒，仍不并发运行，30秒是timer周期而非严格实时保证。通过同轮复核时记healthy及复核原因，不发故障告警、不停进程；最终判定失败后，仍按原顺序立即门禁、停止、落盘，再诊断和通知。故障恢复不自动重启旧Claude任务。

此前DIRECT节点直接返回“不适用”只是不支持诊断，不表示健康或故障。本次新增独立物理网卡诊断：配置direct_interface必须先由部署人员核对与实际节点出口一致，不能填写lo或TUN设备；SO_BINDTODEVICE后回读确认，再测服务器TCP、SOCKS协商、认证、目标连接、TLS、HTTP、出口。绑定或路径未确认不发送凭据；只输出阶段和异常类型，不输出账号密码/异常原文。经机场的旧诊断继续用管理API确认链路，不切换任何代理组。

验证：新增9项回归先在旧实现复现4项失败，修复后全量22项测试通过，独立代码复核亦通过；实际root只读DIRECT诊断对ifconfig.me和api.ipify.org均走完全部阶段，已不再跳过。测试覆盖单次TLS失败独立复核、两次失败、出口不符、HTTP错误、无Webshare备用路由、路由变化、绑定失败不发凭据、TLS阶段归因和秘密不外泄。没有对生产网络做断网注入、没有用真实Claude任务做故障kill验证。
