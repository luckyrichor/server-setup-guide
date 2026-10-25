# Tailscale

现场正在运行，主要用于个人设备之间的加密互联。没有发布 Exit Node、没有选择其他 Exit Node、没有发布子网路由、没有启用 App Connector、Tailscale SSH、Serve/Funnel。
网络级 MagicDNS 已开启，但服务器 accept-dns=false；这与其他 Mac/Windows 设备的设置相互独立。

按官方平台安装步骤安装，登录并加入自己的 tailnet；不要复制旧节点密钥或设备地址。

```bash
tailscale version
tailscale status
tailscale dns status
tailscale serve status
tailscale funnel status
ip rule show
ip route show table 52
```

普通 SSH：`ssh serveruser@TAILSCALE_IP`；服务需监听可达地址、访问策略/防火墙需允许，仍使用原 SSH 认证。
无需启用 Tailscale SSH 或出口节点。用 `ssh serveruser@DEVICE_NAME` 时，客户端需接受 Tailscale DNS。
Mac 菜单栏 Tailscale → Settings/Preferences → Use Tailscale DNS settings；`dscacheutil -q host -a name DEVICE_NAME` 验证。

选择出口节点不是填写 HTTP 代理端口：远端设备需运行 Tailscale、开启转发、发布出口、管理员批准；本机再选择它。
同一 tailnet 可以包含不同登录用户，取决于邀请和策略，不要求同一个登录账号。

出口节点默认承接互联网流量；App Connector 可对指定域名发现的 IP 发布路由。它们与 Clash 域名/协议规则不同。
Webshare 是 HTTP/SOCKS 代理，不能安装 Tailscale，无法直接作为 Exit Node；可以用自有服务器连接两者，但转发和路由需另配。

与 Mihomo TUN 并用时必须实际检查路由优先级。现场 table 52 的设备路由先于 Mihomo 接管；普通互联网请求仍受 Mihomo/系统路由控制。
切勿仅凭“安装了 Tailscale”断言全部上网流量经它转发。

参考：https://tailscale.com/docs/features/exit-nodes 和 https://tailscale.com/docs/features/magicdns 。
