# 新服务器部署顺序

## 基线

现场为 Ubuntu、systemd + systemd-networkd、网卡 eth0；系统时区 America/New_York。
Node v24.21.0、Mihomo v1.19.31、Tailscale 1.102.5、Claude Code 2.1.309、Codex CLI 0.164.0、lark-cli 1.0.96。
版本是现场记录，不等于这些版本未来仍可下载或应永远锁定。

```bash
sudo apt-get update
sudo apt-get install git curl jq python3 python3-yaml dnsutils iproute2 nftables openssh-server ca-certificates
ip -br addr
networkctl status
resolvectl status
timedatectl
```

新机器先设置 SSH 密钥、云安全组及 VNC/串口恢复方式。不要复制旧机器的 IPv6 地址、网关、网卡名或防火墙。
本文使用 `serveruser` 作为用户占位符；更改所有模板中的 `/home/serveruser`、`User=serveruser`。

## 网络先行

1. 从 Mihomo 官方发行版安装与架构匹配的二进制至 `/usr/local/bin/mihomo`，先 `mihomo -v`。
2. 私下准备机场订阅和 Webshare 参数，文件 0600，所在目录 0700。
3. 在本机监听端口验证普通代理，不先启用 TUN。
4. 调整生成器的网卡、云 DNS、TUN 排除网段和端口回程保护，参见 network.md。
5. 确认独立 SSH 恢复通道，再启用 TUN、测试 DNS 和两跳。
6. 安装用户级运维任务，最后启用会终止任务的第二跳监测。

## 用户服务

```bash
sudo loginctl enable-linger serveruser
mkdir -p ~/.config/systemd/user
# 先编辑模板，再复制需要的 unit；不要直接批量启动全部样本。
systemctl --user daemon-reload
systemctl --user enable --now NAME.timer
systemctl --user list-timers --all
```

linger 使用户退出 SSH 后定时任务仍可运行。不需要为每个用户重新启动系统。
依赖 NVM 的 unit 必须显式设置 PATH 或 Node 的绝对路径，不能依赖交互式 .bashrc。

## 实际安装与参考代码

本项目的 watcher 源码已在现场安装；Mihomo 控制器和生成器为既有部署的脱敏参考，使用前核对差异。
不要先安装会改网络的所有 root unit：控制器依赖部署元数据、原稳定代理、网络恢复验证和正确的工作目录。
全新机器尚未完成一遍端到端重建；遇到不匹配应先做离线和并行测试，不能越过 hash/状态保护。
