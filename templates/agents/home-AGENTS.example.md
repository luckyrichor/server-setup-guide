# 服务器公共开发约定

## 共享大模型凭据

- 用户已授权本服务器各项目按需使用火山引擎 Ark API。共享凭据文件：`/home/serveruser/.config/llm/volcengine.env`，变量：`ARK_API_KEY`。
- 用户已授权本服务器各项目按需使用腾讯云 TokenHub API。共享凭据文件：`/home/serveruser/.config/llm/tencent.env`，变量：`TENCENT_API_KEY`、`TENCENT_BASE_URL`。
- 项目需要大模型时按需注入环境变量，不必重复索取密钥。可使用 `with-ark COMMAND`、`with-tencent COMMAND`，或 `with-llm COMMAND` 同时注入两家；已有非空环境变量优先。腾讯云包装器兼容提供 `TOKENHUB_API_KEY`，Base URL 为 `https://tokenhub.tencentmaas.com/v1`。
- 不输出密钥，不将其写入代码、Git、文档、日志、客户端或镜像；不使用 cat/env/printenv/shell 调试追踪展示凭据。
- 不给所有进程全局注入，不自动覆盖已有项目凭据，不重启无关服务。
- 模型和 API 地址按项目配置选择；凭据存在不代表调用已经验证。
- 共享目录权限 700、凭据权限 600，仅 serveruser 和 root 可读。其他账号需单独安排受限访问，不放宽共享文件权限。

本文件适用于 /home/serveruser 下的项目，项目自己的更具体约定仍须遵守。

## 飞书 bridge 等待用户验收

- 需要用户在本轮执行期间回复（如 Clash 发布后的 SSH 验收）时，不能只使用 commentary 或工具进度卡。须用当前 profile 的 `lark-cli im +messages-send --as bot` 向当前 chat_id 发送独立文字消息，核对发送成功及 message_id 后才开始计时等待。
- bridge 可能将新用户消息排队，助手应在等待时读取当前聊天的近期消息，只处理提示之后的指定用户回复；不得把旧的“成功”当成本轮验收。
- 提示须立即发送，写明北京时间截止和实际回滚截止。普通进度说明仍可使用 commentary。
