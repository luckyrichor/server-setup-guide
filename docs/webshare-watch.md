# Claude 第二跳网络监测

## 授权后的最终语义

用户要求：不论仅 Webshare、全面两跳、名单两跳，都必须确认 Webshare 出口；只走第一跳也算失败。
失败时在配置的飞书私聊发通知，并立即终止**故障首次发现时已存在**的 Claude CLI 和可识别子进程。
同一次持续故障中，后来启动的任务不再拦截；成功恢复后不重启旧任务，重新布防以处理下一次新故障。
没有修改 bridge、模型检查 timer 或任何 CLI 启动入口，没有添加启动门禁。

## 检测链路

1. 从私有 Mihomo 配置读取管理密钥，用 localhost API 查看运行 mode、proxies、rules。
2. 核对活动规则存在通向对应 Webshare SOCKS5 的探测路径，不能只看到配置里有一个闲置 Webshare 节点就通过。
3. 与 checkws 一样，强制 HTTP 本地代理请求 https://ifconfig.me/ip，IPv4，连接超时3秒、请求总超时10秒，无重试。
4. 要求返回有效 IP 且与 expected_ip 完全一致；再检查一次运行模式仍具备 Webshare 路径。
5. 无法确认/超时/认证失败/IP不符/只走第一跳均为失败。

mode=rule、global、direct 均有明确处理；不认识的模式拒绝通过。自定义复杂规则/代理组可能保守判失败，迁移后需补对应支持和测试。
这不是完整 Mihomo 规则模拟器；最终出口实测是关键证据。相同出口服务必须使用稳定 IP，轮换住宅出口应先设计新的验证方式。
服务器目前采用从 Webshare server 取得的固定 expected_ip；更换账号/IP 后必须同步私有 watcher 配置。

## 故障状态机

```text
健康 → 首次失败 → 快照并停止当前任务 → 当前私聊通知
                     ↓
                  持续失败：只检测，通知未送达则重试，不再停止新任务
                     ↓
                  恢复健康：重新布防，不启动旧任务
                     ↓
                  下一次新失败：重新快照并停止当时任务
```

只按进程可执行文件/argv0/comm 识别 Claude，不按任意命令行包含“claude”匹配，避免误杀其他进程。
以 /proc 父子关系记录子进程；pidfd + 启动时间核对防止 PID 复用误杀。SIGKILL 直接终止，未完成工作可能中断。
root oneshot 可检查不同系统账号的 Claude；不停止 bridge、Codex 独立会话、Mihomo 或用户 timers。
独立 Codex 不受影响；若 Codex 是某个 Claude 任务仍关联的子进程，则属于那次任务的停止范围。
已经脱离父进程/成为其他服务的后台任务不能仅凭现存父子关系可靠追溯，需具体服务额外登记。

## 安装

依赖：Linux pidfd、Python3、PyYAML、curl、lark-cli、可用的 Mihomo API 与正确绑定的 codex profile。

```bash
sudo apt-get install python3-yaml curl
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
sudo install -m 644 templates/systemd/claude-webshare-watch.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now claude-webshare-watch.timer
sudo systemctl start claude-webshare-watch.service
sudo systemctl status claude-webshare-watch.timer
sudo journalctl -u claude-webshare-watch.service -n 10 --no-pager
```

状态在 /var/lib/claude-webshare-watch/state.json，root 0600；只有健康状态、原因、PID 及通知状态，没有代理账号密码。
通知在 serveruser 对应的普通用户下调用 bridge-bound lark-cli --as bot，不使用用户文档身份，不将 root 凭据或模型环境注入 CLI。
notification_env 只保存 bridge 必需的5个上下文变量；不要从其他 profile 复制密钥或自行 bind。

停用：`sudo systemctl disable --now claude-webshare-watch.timer`。这不会重启任何已停止任务。
不要随意删除故障状态：删除后下一轮持续失败会被视作新事件，再停止当时任务。

## 验证与局限

- 单元测试覆盖规则模式、首跳模式、GLOBAL、持续故障只停止一次、恢复重新布防、通知重试、PID复用保护。
- 真实 SIGKILL 只在测试创建的 sleep 子进程验证，没有人为制造生产断网或停止用户真实任务。
- 现场 probe-only 和启用后定时运行均确认 Webshare出口，通知在目标私聊实测成功。
- 30 秒为 timer 周期；检测/调度耗时叠加，不能保证故障瞬间停止。服务不并发运行，繁忙或通知超时会延迟后续轮次。
- ifconfig.me 不可用也会按失败处理，这是用户选择的一次失败即停止策略；没有双站点容错。
- 这个任务不阻断网络，不证明没有 DNS/IPv6/其他域名绕行，也不保证所有 Claude 请求的域名都在两跳名单中。
