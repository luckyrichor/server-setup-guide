# 验收、检测与恢复

## 不改变配置的检查

```bash
/usr/local/bin/mihomo -v
sudo /usr/local/libexec/mihomo-tx-control status
systemctl is-active mihomo-tx-candidate.service
ip rule show
ip route show table 20220
resolvectl dns eth0
tailscale status
systemctl --user list-timers --all
```

两跳验证必须同时确认出口 IP 和 Mihomo 命中规则/连接链；单看HTTP200不够。
访问不同域名可能直连/第一跳/两跳，因此不能用任意一个IP查询站概括整个系统出口。
ifconfig.me 是现场两跳探测目标；api.ipify.org 通常沿原代理兜底，但需按当前规则确认；国内网站可能直连。

## 常见故障

| 现象 | 先检查 |
|---|---|
| checkws 超时 | 本地端口、当前第一跳、Webshare认证/目标连接；超时本身无法确定故障在哪一段 |
| 出口不匹配 | 当前mode/组选择、域名规则、NO_PROXY及是否绕过TUN |
| CLI模型不可用 | 认证、额度、TLS/网络；bridge在线不等于模型可用 |
| 飞书无消息 | 应用权限、群@、允许用户/群规则、长连接、profile绑定 |
| systemd PATH错误 | unit显式Node/lark-cli路径；不要依赖.bashrc |
| 代理重启后SSH受影响 | VNC、回程保护、DNS恢复、cleanup_errors；不要清空未知网络规则 |
| DNS启用仍有直连 | 系统例外、路由排除、应用DoH、容器及IPv6，需实际抓包验证 |
| 后续Claude又启动 | 按用户最新要求允许；watcher同一次故障不重复停止，新故障才重新触发 |

Claude网络中断后会话通常保存在本地；恢复时可以继续/恢复会话，但不保证最后一次请求未被服务端执行。
超时后重复提交有重复操作风险；不要把请求失败等同于对方完全没收到。

## 发布验收不同于连通性检查

维护流程要求全新SSH连接，最好来自另一网络出口；原SSH连接不断不证明新路由正确。
恢复目标为原普通代理，网络可用不等于Webshare仍在链路中。新watcher会将仅第一跳识别为失败。
文档中所有“现场成功”均不代表已做新机器完整部署或生产故障注入。
