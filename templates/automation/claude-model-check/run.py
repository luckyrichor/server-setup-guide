#!/usr/bin/env python3
"""Ask Claude Code which model it is and send the answer to Feishu."""
import datetime
import json
import os
from pathlib import Path
import subprocess
import tempfile
from zoneinfo import ZoneInfo

ROOT = Path('/home/serveruser/.local/share/claude-model-check')
CHAT_ID = 'REPLACE_RESOURCE_ID'  # 与「tx的Claude助手」的私聊
env = os.environ.copy()
env.update(json.loads((ROOT / 'environment.json').read_text()))
env['PATH'] = '/home/serveruser/.nvm/versions/node/v24.21.0/bin:/home/serveruser/.local/bin:/usr/local/bin:/usr/bin:/bin'
now = datetime.datetime.now(ZoneInfo('Asia/Shanghai'))
prompt = '你是什么模型？请用中文简短回答。仅根据你实际可确认的运行身份回答；不能确认具体版本就说明无法确认，不要猜测。'
header = f'Claude 模型定时询问 · {now:%Y-%m-%d %H:%M}（北京时间）'
with tempfile.TemporaryDirectory(prefix='claude-model-check-') as tmp:
    try:
        # No tools, no session file: a plain question in an empty directory.
        result = subprocess.run(
            ['claude', '-p', prompt, '--output-format', 'json', '--tools', '',
             '--no-session-persistence'],
            cwd=tmp, env=env, capture_output=True, text=True, timeout=240)
        if result.returncode != 0:
            raise RuntimeError('Claude 调用失败')
        data = json.loads(result.stdout)
        answer = str(data.get('result') or '').strip()
        if data.get('is_error') or not answer:
            raise RuntimeError('Claude 未返回回答')
        models = ', '.join(data.get('modelUsage', {}).keys())
        message = f'{header}\n问题：你是什么模型？\n回答：{answer[:2500]}'
        if models:
            message += f'\nAPI 实际调用模型：{models}'
    except (subprocess.TimeoutExpired, RuntimeError, OSError, ValueError):
        message = f'{header}\n本次调用失败或超时，未获得模型回答。'
    send = subprocess.run(
        ['lark-cli', 'im', '+messages-send', '--as', 'bot',
         '--chat-id', CHAT_ID, '--text', message,
         '--idempotency-key', f'claude-model-{now:%Y%m%d-%H%M}', '--json'],
        env=env, capture_output=True, text=True, timeout=45)
    if send.returncode:
        raise SystemExit('发送失败；请检查 claude-model-check.service 状态和飞书连接。')
    print(message)
    print('飞书发送成功。')
