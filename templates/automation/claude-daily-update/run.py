#!/usr/bin/env python3
"""Check the npm `stable` tag of Claude Code, update only when newer, then notify Feishu."""
import datetime
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
from zoneinfo import ZoneInfo

ROOT = Path('/home/serveruser/.local/share/claude-daily-update')
BIN = '/home/serveruser/.nvm/versions/node/v24.21.0/bin/'
env = os.environ.copy()
env.update(json.loads((ROOT / 'environment.json').read_text()))
env['PATH'] = BIN + ':/home/serveruser/.local/bin:/usr/local/bin:/usr/bin:/bin'
check_only = '--check-only' in sys.argv

def run(args, timeout=60):
    child = subprocess.Popen(args, env=env, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        out, err = child.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(child.pid, signal.SIGKILL)
        child.communicate()
        raise RuntimeError('命令运行超时')
    if child.returncode:
        # Do not expose npm configuration, tokens or network error payloads.
        raise RuntimeError(f'{Path(args[0]).name} 执行失败，退出码 {child.returncode}')
    return out.strip()

def version(value):
    if not re.fullmatch(r'\d+\.\d+\.\d+', value):
        raise RuntimeError('版本格式异常，停止自动更新')
    return tuple(map(int, value.split('.')))

with (ROOT / 'run.lock').open('a') as lock:
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit('已有更新任务运行，本次跳过。')
    now = datetime.datetime.now(ZoneInfo('Asia/Shanghai'))
    failed = False
    try:
        current = run([BIN + 'claude', '--version']).split()[0]
        latest = json.loads(run([BIN + 'npm', 'view', '@anthropic-ai/claude-code', 'dist-tags.stable',
                                 '--json', '--registry=https://registry.npmjs.org']))
        newer = version(latest) > version(current)
        if check_only:
            print(json.dumps({'current': current, 'latest_stable': latest,
                              'update_available': newer, 'mode': 'check-only'}, ensure_ascii=False))
            raise SystemExit(0)
        if newer:
            run([BIN + 'npm', 'install', '-g', '@anthropic-ai/claude-code@' + latest,
                 '--registry=https://registry.npmjs.org', '--no-audit', '--no-fund'], timeout=600)
            actual = run([BIN + 'claude', '--version']).split()[0]
            if actual != latest:
                raise RuntimeError('更新后版本校验不一致')
            result = f'更新成功：{current} → {actual}。\n新启动的 Claude 进程将使用新版。'
        else:
            result = f'无需更新。当前版本：{current}；npm 稳定版（stable）：{latest}。'
    except (RuntimeError, OSError, ValueError) as error:
        if check_only:
            raise SystemExit('只读版本检查失败。')
        failed = True
        result = f'检查或更新失败：{error}'
    message = f'Claude CLI 每日更新 · {now:%Y-%m-%d %H:%M}（北京时间）\n{result}'
    (ROOT / 'last-result.json').write_text(json.dumps(
        {'checked_at': now.isoformat(), 'failed': failed, 'result': result}, ensure_ascii=False, indent=2))
    print(message)
    run(['lark-cli', 'im', '+messages-send', '--as', 'bot',
         '--chat-id', 'REPLACE_RESOURCE_ID', '--text', message,
         '--idempotency-key', f'claude-daily-update-{now:%Y%m%d-%H%M}', '--json'], timeout=45)
    print('飞书通知发送成功。')
    raise SystemExit(1 if failed else 0)
