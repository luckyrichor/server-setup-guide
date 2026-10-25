#!/usr/bin/env python3
import datetime
import json
import os
from pathlib import Path
import subprocess
import tempfile
from zoneinfo import ZoneInfo

ROOT = Path('/home/serveruser/.local/share/codex-model-check')
env = os.environ.copy()
env.update(json.loads((ROOT / 'environment.json').read_text()))
env['PATH'] = '/home/serveruser/.nvm/versions/node/v24.21.0/bin:/home/serveruser/.local/bin:/usr/local/bin:/usr/bin:/bin'
now = datetime.datetime.now(ZoneInfo('Asia/Shanghai'))
prompt = '你是什么模型？请用中文简短回答。仅根据你实际可确认的运行身份回答；不能确认具体版本就说明无法确认，不要猜测。不要使用工具、读文件或联网。'
with tempfile.TemporaryDirectory(prefix='codex-model-check-') as tmp:
    answer_file = Path(tmp) / 'answer.txt'
    try:
        result = subprocess.run(
            ['codex', 'exec', '--ephemeral', '--skip-git-repo-check', '-s', 'read-only',
             '--color', 'never', '-C', tmp, '-o', str(answer_file), prompt],
            env=env, capture_output=True, text=True, timeout=240)
        if result.returncode != 0 or not answer_file.exists():
            raise RuntimeError('Codex 调用失败')
        answer = answer_file.read_text().strip()
        if not answer:
            raise RuntimeError('Codex 未返回回答')
        requested_model = next((line.split(':', 1)[1].strip()
                                for line in result.stderr.splitlines()
                                if line.startswith('model:')), '')
        message = f'模型定时询问 · {now:%Y-%m-%d %H:%M}（北京时间）\n问题：你是什么模型？\n回答：{answer[:2500]}'
        if requested_model:
            message += f'\nCLI 请求模型：{requested_model}（配置标识）'
    except (subprocess.TimeoutExpired, RuntimeError, OSError):
        message = f'模型定时询问 · {now:%Y-%m-%d %H:%M}（北京时间）\n本次调用失败或超时，未获得模型回答。'
    send = subprocess.run(
        ['lark-cli', 'im', '+messages-send', '--as', 'bot',
         '--chat-id', 'REPLACE_RESOURCE_ID', '--text', message,
         '--idempotency-key', f'codex-model-{now:%Y%m%d-%H%M}', '--json'],
        env=env, capture_output=True, text=True, timeout=45)
    if send.returncode:
        raise SystemExit('发送失败；请检查 codex-model-check.service 状态和飞书连接。')
    print(message)
    print('飞书发送成功。')
