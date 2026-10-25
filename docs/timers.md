# 定时任务清单

核对日期 2026-10-25。下列常用任务显式使用 Asia/Shanghai，**时间均为北京时间**；系统为 America/New_York，systemctl 显示的 EDT/EST 不能直接当北京时间。

| 用户级 timer | 时间 | 内容/入口 |
|---|---|---|
| claude-model-check | 每天 07:00、13:00 | 调用 Claude 查询模型身份并发飞书；~/.local/share/claude-model-check/run.py |
| codex-model-check | 每天 07:00、13:00 | 调用 Codex 查询模型身份并发飞书；对应目录 run.py |
| updatesanmao-daily | 每天 07:30 | 下载并校验机场订阅，只保存待发布文件，不应用 |
| claude-daily-update | 每天 08:00 | 检查/更新 Claude CLI npm 包 |
| codex-weekly-update | 每天 08:00 | 检查/更新 Codex CLI；名字虽叫 weekly，实际是每天 |
| daily-system-check | 每天 10:00 | sys/checkcc/checkws 原始检测结果发飞书 |
| tencent-stock-watch | 每半小时 | 活动库存接口查询；仅描述运维机制，不提供业务账号/请求标识 |
| winter-time-reminder | 2026-11-01 10:00 一次 | 冬令时提醒；Persistent=true，其余上列常规任务多为 false |

模型检查有独立环境 JSON、通知环境 JSON，均在仓库外重建；不要复制原始认证文件。
Claude 模型检查非交互请求超时约 240 秒；服务总超时 5 分钟；失败文案由本地脚本生成，不是模型回答。
CLI 更新服务超时 15 分钟，网络健康报告服务超时 4 分钟。
模板代码见 templates/automation/；如脚本引用 lark-env.json/environment.json，需私下填写当前 profile 环境。

| 系统级任务 | 频率/行为 |
|---|---|
| claude-webshare-watch（本次新增） | 每 30 秒，10 秒出口请求超时；状态机详见 webshare-watch.md |
| claude-webshare-guard（常驻服务） | 故障期间每0.25秒清理可识别Claude进程；常用安装路径由AppArmor门禁提前拦截 |
| mihomo-tx-health | 每 30 秒检查 TUN/DNS，故障时可能恢复普通代理 |
| mihomo-tx-boot-confirm | 首次新版本重启确认窗口，超时恢复 |
| tx-mihomo-activation-rollback | 激活配置后的恢复窗口；正常约15分钟，发布封装临时约20分钟 |
| TLS 证书续期 | 两个已有应用的独立 timer；属于应用维护，只迁移通用续期机制，不列业务细节 |

系统自带 apt-daily、apt-daily-upgrade、logrotate、fstrim、dpkg-db-backup、sysstat、fwupd、tmpfiles 等由发行版维护，不将旧时间戳复制到新机器。
root crontab 存在云厂商 stargate 守护的 5 分钟任务；新机器由云镜像管理，不复制厂商 agent 的安装路径和账号状态。
用户 crontab 当前未发现条目；定时工作以 systemd timer 为主。

```bash
systemctl --user list-timers --all
systemctl list-timers --all
systemctl --user cat codex-weekly-update.timer
systemctl --user start daily-system-check.service
systemctl --user stop NAME.timer
systemctl --user disable NAME.timer
```

不要直接运行所有服务来“测试”：模型检查会调用模型，更新会改变版本，恢复服务会改网络。
与业务下载有关的常驻 supervisor 不是定时器；它可能全局切换机场组，发生切换可影响其他进程的新连接。
