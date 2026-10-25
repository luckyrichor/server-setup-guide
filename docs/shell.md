# Shell 函数与网络自检

可读实现见 `templates/bashrc-infrastructure.sh`。这是从现场 .bashrc 提取的基础设施片段，不含完整用户 shell 配置。

| 函数 | 行为与边界 |
|---|---|
| proxy_on | 设置 http_proxy/https_proxy 为本地 7890，all_proxy 为本地 SOCKS5；配置本地/云内网 no_proxy |
| proxy_off | 清除上述 shell 变量；**不会关闭系统 TUN** |
| proxy_status | 查看当前 shell 的代理变量，并请求网站测试；不是系统全流量状态 |
| sys | free/df 显示内存和根分区使用情况 |
| cbd | 为 user bus 设置 runtime 路径后管理可选 CodeBuddy daemon；不需要该软件可移除 |
| checkws | 强制经本地 HTTP 代理查询 ifconfig.me/ip，核对预期 Webshare IPv4 |
| updatesanmao | 下载并校验订阅到 base.upload.yaml，不应用、不重启 |
| checkcc | 调用独立 HTTP/出口报告脚本，评估结果不是厂商账号风控的确认结论 |

`checkws` 使用 curl -q 避免 .curlrc 干扰，-4 强制 IPv4，连接超时 3 秒、总超时 20 秒，无重试；显式代理和 `--noproxy ''` 防止被 NO_PROXY 绕过。
返回值为 0 才通过；匹配 IP 由 `CHECKWS_EXPECTED_IP` 覆盖。样本里 192.0.2.10 是文档示例地址，必须替换。

```bash
export CHECKWS_EXPECTED_IP='YOUR_WEBSHARE_EXIT_IPV4'
checkws
proxy_status
sys
```

现场在交互 shell 启动时自动 proxy_on、checkws；systemd 不读取交互 .bashrc。
因此新监测直接复用 curl/出口核对逻辑，不通过 `bash -i` 加载整份启动脚本，避免打印提示、阻塞或执行不相关命令。

安装时选取需要的函数放入 .bashrc，勿覆盖原文件。`with-ark`、`with-tencent`、`with-llm` 是可选凭据注入包装器：只对指定子命令按需注入，真实环境文件放私有目录，禁止输出或复制。
