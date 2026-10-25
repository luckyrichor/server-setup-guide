#!/usr/bin/env python3
"""Run the current bashrc function and report its sanitized result to Feishu."""
import datetime
import json
import os
from pathlib import Path
import re
import subprocess
from zoneinfo import ZoneInfo

root = Path('/home/serveruser/.local/share/updatesanmao-daily')
env = os.environ.copy()
env.update(json.loads((root / 'environment.json').read_text()))
env['PATH'] = '/home/serveruser/.nvm/versions/node/v24.21.0/bin:/home/serveruser/.local/bin:/usr/local/bin:/usr/bin:/bin'
now = datetime.datetime.now(ZoneInfo('Asia/Shanghai'))
code = -1
detail = ''
try:
    bashrc = Path('/home/serveruser/.bashrc').read_text()
    functions = re.findall(r'^updatesanmao\(\) \{\n.*?^\}', bashrc, re.M | re.S)
    if len(functions) != 1:
        raise ValueError('未找到唯一的 updatesanmao 函数定义')
    # Only load this function: interactive bashrc startup has unrelated effects.
    result = subprocess.run(
        ['/bin/bash', '--noprofile', '--norc', '-c', functions[0] + '\nupdatesanmao'],
        env=env, capture_output=True, text=True, timeout=120)
    code = result.returncode
    # Never forward arbitrary shell output, subscription URLs or YAML credentials.
    for line in (result.stdout + '\n' + result.stderr).splitlines():
        if line.startswith(('✅ 第一跳机场订阅', '❌ 第一跳机场订阅', '待发布文件：')):
            detail += re.sub(r'https?://\S+', '[已隐藏链接]', line)[:400] + '\n'
    if not detail:
        detail = '函数已结束，未返回可展示的订阅状态。'
except subprocess.TimeoutExpired:
    detail = '运行超过 120 秒，已停止本次调用。'
except (OSError, ValueError):
    detail = '无法读取或执行 updatesanmao，请检查函数定义及运行环境。'

status = '成功' if code == 0 else '失败'
message = f'订阅定时下载 · {now:%Y-%m-%d %H:%M}（北京时间）\n任务：updatesanmao\n结果：{status}\n{detail.strip()}'
message += '\n仅下载待发布订阅，不自动切换运行配置。'
sent = subprocess.run(
    ['lark-cli', 'im', '+messages-send', '--as', 'bot',
     '--chat-id', 'REPLACE_RESOURCE_ID', '--text', message,
     '--idempotency-key', f'updatesanmao-{now:%Y%m%d-%H%M}', '--json'],
    env=env, capture_output=True, text=True, timeout=45)
print(message)
if sent.returncode:
    raise SystemExit('飞书通知发送失败，请检查当前 codex profile 和网络。')
print('飞书通知发送成功。')
raise SystemExit(0 if code == 0 else 1)
