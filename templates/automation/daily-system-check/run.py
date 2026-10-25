#!/usr/bin/env python3
"""Send the unmodified output of three current bashrc functions to Feishu."""
import datetime
import json
import os
from pathlib import Path
import re
import signal
import subprocess
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
env = os.environ.copy()
env.update(json.loads((ROOT / 'environment.json').read_text()))
env['PATH'] = '/home/serveruser/.nvm/versions/node/v24.21.0/bin:/home/serveruser/.local/bin:/usr/local/bin:/usr/bin:/bin'
bashrc = Path('/home/serveruser/.bashrc').read_text()
definitions = []
for name in ('sys', 'checkcc', 'checkws'):
    matches = re.findall(r'^' + name + r'\(\) \{\n.*?^\}', bashrc, re.M | re.S)
    if len(matches) != 1:
        raise SystemExit(f'未找到唯一的 {name} 函数定义')
    definitions.append(matches[0])
# Load only the requested definitions, avoiding automatic startup execution.
command = '\n'.join(definitions) + '\nstatus=0\nprintf \'%s\\n\' \'sys\'\nsys || status=1\nprintf \'\\n%s\\n\' \'checkcc\'\ncheckcc || status=1\nprintf \'\\n%s\\n\' \'checkws\'\ncheckws || status=1\nexit "$status"\n'
process = subprocess.Popen(
    ['/bin/bash', '--noprofile', '--norc', '-c', command], env=env,
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    start_new_session=True)
try:
    output, _ = process.communicate(timeout=150)
except subprocess.TimeoutExpired:
    os.killpg(process.pid, signal.SIGKILL)
    output, _ = process.communicate()
# Preserve function output, adding only function names and section separators.
if output:
    now = datetime.datetime.now(ZoneInfo('Asia/Shanghai'))
    sent = subprocess.run(
        ['lark-cli', 'im', '+messages-send', '--as', 'bot',
         '--chat-id', 'REPLACE_RESOURCE_ID', '--text', output,
         '--idempotency-key', f'daily-system-check-{now:%Y%m%d-%H%M%S}', '--json'],
        env=env, capture_output=True, text=True, timeout=45)
    print(output, end='')
    if sent.returncode:
        raise SystemExit('飞书通知发送失败，请检查 codex profile 和网络。')
    print('飞书通知发送成功。')
else:
    raise SystemExit('函数未打印任何内容，未发送空消息。')
raise SystemExit(process.returncode if process.returncode >= 0 else 1)
