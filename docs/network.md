# Mihomo / Clash 网络

## 数据流与现状

当前运行三档模式：直连；机场第一跳；机场 + Webshare SOCKS5 两跳。Webshare 节点使用 `dialer-proxy` 指向机场组。
该配置没有自动失败降级。Webshare 失败时，命中两跳规则的请求报错/超时，不继续匹配后面的 MATCH。
存在显式拒绝规则。Webshare 不支持 UDP；对应范围 UDP 443 拒绝，支持的应用可回退 TCP。

配置输入：

| 文件 | 用途 |
|---|---|
| `~/.config/mihomo/tx/base.upload.yaml` | 下载的待发布机场订阅 |
| `~/.config/mihomo/tx/base.yaml` | 已确认的生成输入 |
| `~/.config/mihomo/tx/webshare-dns.js` | 账号、域名/IP 名单、DNS 和模式逻辑 |
| `~/.config/mihomo/tx/build-config.py` | 调用 JS，追加 TX 系统规则并生成最终 YAML |
| `/var/lib/mihomo-tx/active/config.yaml` | 正式运行 YAML，禁止直接覆盖 |
| `/var/lib/mihomo-tx/deployment.json` | hash、内核版本、回滚和启动确认元数据 |
| `~/.config/mihomo/config.yaml` | 原稳定普通代理，回滚目标 |

### 本地接口

mixed HTTP/SOCKS：127.0.0.1:7890；控制 API：127.0.0.1:19090（Bearer secret）；DNS：127.0.0.1:53。
控制密钥每次生成可能变化，API 客户端必须读取当前有效配置，不能写死到仓库。
localhost 监听并不阻止其他本地用户访问；独立账号隔离还需文件权限和管理接口访问限制。

## 生成示例（只写暂存文件，不生效）

```bash
mkdir -p ~/.config/mihomo/tx
chmod 700 ~/.config/mihomo/tx
# 将订阅私下保存为 base.yaml，并填写 current.example.js 的占位符。
cp templates/mihomo/apply-extension.cjs ~/.config/mihomo/tx/
cp templates/mihomo/build-config.py ~/.config/mihomo/tx/
# 先将 build-config.py 内 serveruser、eth0、DNS 等改成本机参数。
python3 ~/.config/mihomo/tx/build-config.py proxy ~/.config/mihomo/tx/candidate.yaml
/usr/local/bin/mihomo -t -d ~/.config/mihomo -f ~/.config/mihomo/tx/candidate.yaml
```

内核检查通过不证明账号可用。测试普通代理时使用独立工作目录、缓存与高位端口，不能与现有实例争抢 7890。

## TUN 与系统例外

现场使用 mixed 栈、auto-route、auto-redirect、strict-route；TUN 设备 mihomo-tx，路由表 20220，规则优先级 19000–19010。
TCP 源端口 22/80/443 的回程保护规则优先走 main，避免服务器 SSH/HTTP 回包被代理误接管。
生成器在 JS 之后追加 apt/apt-get/unattended-upgrade、软件源域名、云内网域名的 DIRECT 和 DNS 例外。
TUN 还排除云内网、容器网段等：这些是平台专用设置，不应跨机器直接复制。

因此“扩展里所有 TCP 走 Webshare”不等于整个系统无直连；未接管、排除、后置例外均需单独检查。

## 四模式草稿（未启用）

`templates/mihomo/webshare-dns.four-modes.DRAFT.js` 按用户指定顺序：

1. 只走 Webshare：ONLY_SECOND_HOP=true，优先级最高。TCP 直连 Webshare，其他协议拒绝；DNS 强制经 Webshare。
2. 按规则两跳：false/true/true；名单 TCP 走机场+Webshare，原分流保留。
3. 只走第一跳：false/false/任意；保留原 DIRECT/REJECT，不额外阻断 QUIC。
4. 原代理范围全部两跳：false/true/false；原机场 TCP 追加 Webshare，原直连仍保留。

所有模式 DNS 增强固定开启；涉及 Webshare 的模式自动添加对应范围 QUIC 阻断。
Webshare 无 UDP，关闭阻断也不会产生 UDP 转发能力。草稿尚未实际联网或在新服务器启用。

## 切节点与发布配置不同

修改 `/proxies/{组名}` 的 PUT 选择不停止 Mihomo/TUN：新连接可能用新节点，旧连接可能仍用旧节点。
服务器已有自动下载故障切换器只改第一跳组，检测候选 HTTPS，核对其他选择和配置 hash；不是重启代理。

完整发布则停止候选服务并清理 TUN 路由，再激活配置；期间可能恢复系统直连。
回滚恢复普通代理，不保证保留两跳。不要将“没有自动降级”理解为“重启发布也绝无直连窗口”。

## 正式发布与恢复

参考 [维护流程](mihomo-maintenance-reference.md) 和 `templates/mihomo/publish-tools/`。
迁移后需同步修改这些工具中的家目录/skill 路径，核对所有绝对路径。

1. 编辑前备份源配置；下载订阅不会自动生效。
2. 准备并验证稳定回滚副本；执行 `node --check`、`mihomo -t` 和发布工具 `--check`。
3. 发布建立自动回滚窗口，激活后用第二网络出口新建 SSH 验收。
4. 确认两跳、第一跳、国内直连、DNS 和日志后才 `--accept`。
5. 首次真正重启用 `confirm`，不同于激活 `accept`；不要用现有 SSH 代替新连接验收。

控制器硬编码了现场内核、网络路径和云 DNS；新机器需生成自己的 deployment.json（version=候选 YAML SHA256、kernel_version、enabled、origin_boot_id、prior_ipv6 等），不得复制旧 IPv6/boot_id。
提供控制器源码用于审阅；首次启用前逐项完成 prepare/guard/DNS/recovery 前置条件并确认原稳定服务可用。
禁止通过伪造 phase/删除保护规则绕过失败状态。

## 手机订阅

手机生成器、TX 自用 JS 是独立文件。手机更新只下载已发布 YAML，不执行 TX JS。
若未来更新名单/账号并发布，需分别生成 split/all/first 模式并核对；本次四模式草稿没有同步到任何运行端。
