#!/usr/bin/env python3
"""Check Webshare, block Claude execution during outages, and stop its process trees."""
import argparse
import fcntl
import ipaddress
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import urllib.request

import yaml


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix('.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as out:
        json.dump(value, out, ensure_ascii=False, indent=2)
        out.write('\n')
    os.replace(temporary, path)


def leaf(name, proxies, seen=None):
    seen = set() if seen is None else seen
    if name in seen:
        return None
    seen.add(name)
    node = proxies.get(name, {})
    if node.get('type') in ('Selector', 'URLTest', 'Fallback'):
        return leaf(node.get('now'), proxies, seen)
    return name


def route_uses_webshare(mode, proxies, rules, candidates, host):
    def uses(name):
        return leaf(name, proxies) in candidates
    if mode == 'global':
        return uses('GLOBAL')
    if mode != 'rule':
        return False
    # Existence alone is insufficient: a first-only config may retain an unused node.
    for rule in rules:
        if rule.get('extra', {}).get('disabled'):
            continue
        if not uses(rule.get('proxy')):
            continue
        kind, payload = rule.get('type', '').lower(), rule.get('payload', '').lower()
        if kind == 'match' or (kind == 'network' and payload == 'tcp'):
            return True
        if host.lower() in payload and ('tcp' in payload or kind in ('domain', 'domainsuffix')):
            return True
    return False


def check(settings):
    try:
        config = yaml.safe_load(Path(settings['mihomo_config']).read_text())
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

        def api(path):
            request = urllib.request.Request(settings['controller'] + path,
                headers={'Authorization': 'Bearer ' + str(config['secret'])})
            with opener.open(request, timeout=2) as response:
                return json.load(response)

        runtime = api('/configs')
        proxies = api('/proxies')['proxies']
        rules = api('/rules')['rules']
        expected = str(ipaddress.ip_address(settings['expected_ip']))
        candidates = {p['name'] for p in config.get('proxies', [])
            if p.get('type') == 'socks5' and p.get('server') == settings['webshare_server']
            and proxies.get(p.get('name'), {}).get('type', '').lower() == 'socks5'}
        if not route_uses_webshare(str(runtime.get('mode', '')).lower(), proxies,
                rules, candidates, settings['probe_host']):
            return False, '当前模式未确认使用 Webshare（包含只走第一跳的情况）'
        # Same explicit local proxy + expected exit IP logic as .bashrc checkws.
        result = subprocess.run(['curl', '-q', '-4', '-fsS', '--connect-timeout', '3',
            '--max-time', str(settings.get('probe_timeout', 10)), '--retry', '0',
            '--noproxy', '', '--proxy', settings['proxy_url'], settings['probe_url']],
            capture_output=True, text=True, timeout=settings.get('probe_timeout', 10) + 2)
        if result.returncode:
            return False, 'Webshare 出口请求失败或超时'
        try:
            actual = str(ipaddress.ip_address(result.stdout.strip()))
        except ValueError:
            return False, '出口查询返回无效 IP'
        if actual != expected:
            return False, '出口 IP 与预期 Webshare 不符'
        # Reject a mode/selector change while the probe was in flight.
        after_mode = api('/configs')
        after_proxies = api('/proxies')['proxies']
        after_rules = api('/rules')['rules']
        if not route_uses_webshare(str(after_mode.get('mode', '')).lower(), after_proxies,
                after_rules, candidates, settings['probe_host']):
            return False, '检测期间出口模式发生变化，未能确认第二跳'
        return True, 'Webshare 出口已确认'
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired, yaml.YAMLError):
        return False, '无法读取或确认代理运行状态'


def process_info(pid):
    path = Path('/proc') / str(pid)
    try:
        stat = (path / 'stat').read_text()
        tail = stat[stat.rfind(')') + 2:].split()
        args = (path / 'cmdline').read_bytes().split(b'\0')
        argv0 = args[0].decode(errors='replace') if args else ''
        exe = os.readlink(path / 'exe').removesuffix(' (deleted)')
        comm = (path / 'comm').read_text().strip()
        is_claude = (Path(argv0).name in ('claude', 'claude.exe')
            or Path(exe).name in ('claude', 'claude.exe')
            or '/@anthropic-ai/claude-code/' in exe
            or '/.local/share/claude/versions/' in exe
            or comm == 'claude')
        return {'pid': pid, 'ppid': int(tail[1]), 'start': tail[19], 'claude': is_claude}
    except (OSError, ValueError, IndexError):
        return None


def snapshot():
    processes = {}
    for path in Path('/proc').iterdir():
        if path.name.isdigit():
            entry = process_info(int(path.name))
            if entry:
                processes[entry['pid']] = entry
    selected = {pid for pid, entry in processes.items() if entry['claude']}
    while True:
        children = {pid for pid, entry in processes.items() if entry['ppid'] in selected}
        if children <= selected:
            break
        selected |= children
    return [processes[pid] for pid in selected if pid not in (1, os.getpid())]


def kill_snapshot(targets):
    killed, failed = [], []
    # Pin original identities, so a reused PID or newly launched process is not killed.
    for entry in targets:
        descriptor = None
        try:
            descriptor = os.pidfd_open(entry['pid'])
            current = process_info(entry['pid'])
            if not current or current['start'] != entry['start']:
                continue
            signal.pidfd_send_signal(descriptor, signal.SIGKILL)
            killed.append(entry['pid'])
        except ProcessLookupError:
            pass
        except OSError:
            failed.append(entry['pid'])
        finally:
            if descriptor is not None:
                os.close(descriptor)
    return killed, failed


# Native npm and standalone installs, including future versions in these layouts.
GATE_PATTERNS = (
    '/**/node_modules/@anthropic-ai/claude-code/bin/claude.exe',
    '/**/.local/share/claude/versions/*',
    '/usr/local/bin/claude',
    '/usr/bin/claude',
)


def gate_profile(patterns=GATE_PATTERNS, prefix='claude-webshare-gate'):
    return ''.join('profile '+prefix+'-'+str(i)+' "'+pattern+'" {\n'
        '  deny /** mrwklx,\n  deny network,\n}\n'
        for i, pattern in enumerate(patterns))


def set_gate(settings, blocked):
    """Persistent profile loads closed at boot; healthy checks unload it in kernel."""
    profile = Path(settings.get('gate_profile', '/etc/apparmor.d/claude-webshare-gate'))
    content = gate_profile()
    if not profile.exists() or profile.read_text() != content:
        profile.write_text(content)
        profile.chmod(0o644)
    # /sys is used to avoid treating an already-unloaded profile as an error.
    loaded = Path('/sys/kernel/security/apparmor/profiles').read_text()
    names = ['claude-webshare-gate-'+str(i) for i in range(len(GATE_PATTERNS))]
    present = [name+' (enforce)' in loaded for name in names]
    if (blocked and all(present)) or (not blocked and not any(present)):
        return
    result = subprocess.run(['/usr/sbin/apparmor_parser', '-K', '-r' if blocked else '-R', str(profile)],
        capture_output=True, text=True, timeout=10)
    if result.returncode:
        raise RuntimeError('AppArmor 启动门禁更新失败')



def decision(previous, healthy):
    return 'healthy' if healthy else ('ongoing' if previous.get('incident') else 'incident')


def notify(settings, text, incident_id):
    env = os.environ.copy()
    env.update(settings['notification_env'])
    env['PATH'] = settings['notification_path']
    command = [settings['lark_cli'], 'im', '+messages-send', '--as', 'bot',
        '--chat-id', settings['chat_id'], '--text', text,
        '--idempotency-key', 'ws-watch-' + incident_id]
    if os.geteuid() == 0:
        command = ['runuser', '-u', settings['notification_user'], '--',
            '/usr/bin/env', 'PATH=' + env['PATH']] + [k+'='+v for k,v in settings['notification_env'].items()] + command
    try:
        result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=25)
        parsed = json.loads(result.stdout)
        return result.returncode == 0 and parsed.get('ok') is True
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return False


def run(settings, probe_only=False):
    healthy, reason = check(settings)
    if probe_only:
        print(json.dumps({'healthy': healthy, 'reason': reason}, ensure_ascii=False))
        return 0 if healthy else 1
    path = Path(settings['state_path'])
    try:
        previous = json.loads(path.read_text())
    except (OSError, ValueError):
        previous = {}
    action = decision(previous, healthy)
    state = dict(previous, checked_at=time.time(), healthy=healthy, reason=reason)
    # Publish recovery before unloading: the fallback must not kill newly allowed tasks.
    if healthy:
        atomic_json(path, state)
    try:
        set_gate(settings, not healthy)
        state.pop('gate_error', None)
        state['gate_blocked'] = not healthy
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        healthy = False
        reason = '启动门禁更新失败；持续终止 Claude，需管理员检查 AppArmor'
        action = decision(previous, healthy)
        state.update(healthy=False, reason=reason, gate_error=True)
    if action == 'healthy':
        state['incident'] = False
        # Preserve an unsent outage alert even if network recovers before delivery.
    else:
        targets = snapshot()
        killed, failed = kill_snapshot(targets)
        state.update(last_killed=killed, kill_failed=failed)
    if action == 'incident':
        incident_id = str(time.time_ns())
        state.update(incident=True, incident_id=incident_id, killed=killed, kill_failed=failed)
        state['pending_alert'] = {
            'id': incident_id,
            'text': 'Claude 网络第二跳检测失败：'+reason+'。已停止当时的 Claude CLI 及子进程 '
                +str(len(killed))+' 个；停止失败 '+str(len(failed))+' 个。'
                +('启动门禁异常，正在持续清理新进程；请检查 AppArmor。' if state.get('gate_error')
                  else '已启用故障期间启动拦截，检测恢复后才解除；不会自动重启旧任务。')}
    atomic_json(path, state)
    alert = state.get('pending_alert')
    if alert:
        state['notification_sent'] = notify(settings, alert['text'], alert['id'])
        if state['notification_sent']:
            state.pop('pending_alert', None)
        atomic_json(path, state)
    print(json.dumps({k:state.get(k) for k in
        ('checked_at','healthy','reason','incident','notification_sent')}, ensure_ascii=False))
    return 0


def guard(settings):
    """Catch unrecognized executable layouts while blocked; normal paths are kernel gated."""
    while True:
        try:
            state = json.loads(Path(settings['state_path']).read_text())
            blocked = not state.get('healthy', False)
        except (OSError, ValueError):
            blocked = True
        if blocked:
            kill_snapshot(snapshot())
        time.sleep(0.25)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--probe-only', action='store_true', help='no state change, kill or notification')
    parser.add_argument('--guard', action='store_true', help='continuously stop Claude during failure')
    args = parser.parse_args()
    settings = json.loads(Path(args.config).read_text())
    if args.guard:
        return guard(settings)
    lock = Path(settings['state_path']).with_suffix('.lock')
    lock.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with lock.open('w') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return run(settings, args.probe_only)


if __name__ == '__main__':
    raise SystemExit(main())
