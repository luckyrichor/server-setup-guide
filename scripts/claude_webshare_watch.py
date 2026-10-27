#!/usr/bin/env python3
"""Check Webshare, block Claude execution during outages, and stop its process trees."""
import argparse
import concurrent.futures
import http.client
import socket
import ssl
import sys
import urllib.parse
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
        def request(url, budget):
            return subprocess.run(['curl', '-q', '-4', '-fsS', '--connect-timeout', '8',
                '--max-time', str(budget), '--retry', '0', '--noproxy', '',
                '--proxy', settings['proxy_url'], url], capture_output=True, text=True,
                timeout=budget + 2)

        host = settings['probe_host']
        result = request(settings['probe_url'], settings.get('probe_timeout', 10))
        primary_code = result.returncode
        if result.returncode:
            if result.returncode not in (28, 35, 56):
                return False, 'Webshare 出口请求失败（curl返回码 '+str(result.returncode)+'；未触发超时/TLS/接收错误复核）'
            fallback = urllib.parse.urlsplit(settings.get('fallback_probe_url', 'https://ipinfo.io/ip'))
            if (fallback.scheme != 'https' or not fallback.hostname or fallback.username
                    or fallback.password or fallback.hostname == host):
                return False, '主探测curl返回码 '+str(primary_code)+'；独立复核站点配置无效'
            host = fallback.hostname
            if not route_uses_webshare(str(runtime.get('mode', '')).lower(), proxies,
                    rules, candidates, host):
                return False, '主探测curl返回码 '+str(primary_code)+'；备用站点未确认使用Webshare，不进行复核'
            # One independent request only; never retry wrong exits or route failures.
            result = request(fallback.geturl(), min(10, settings.get('probe_timeout', 10)))
            if result.returncode:
                return False, ('主探测curl返回码 '+str(primary_code)+'；独立站点复核也失败（curl返回码 '
                    +str(result.returncode)+'），需分段诊断')
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
                after_rules, candidates, host):
            return False, '检测期间出口模式发生变化，未能确认第二跳'
        if primary_code:
            return True, '主探测curl返回码 '+str(primary_code)+'；独立站点复核Webshare出口通过'
        return True, 'Webshare 出口已确认'
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired, yaml.YAMLError):
        return False, '无法读取或确认代理运行状态'


def diagnostic_api(settings, config, path, timeout=2):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(settings['controller'] + path,
        headers={'Authorization': 'Bearer ' + str(config['secret'])})
    with opener.open(request, timeout=timeout) as response:
        return json.load(response)


def first_hop_probe(settings, config, proxies, group):
    selected = leaf(group, proxies)
    if selected in (None, 'DIRECT', 'REJECT'):
        return {'ok': None, 'stage': 'first_hop', 'detail': '未选择有效第一跳'}
    try:
        # The named-proxy delay API tests that outbound, without changing any selector.
        path = '/proxies/' + urllib.parse.quote(selected, safe='') + '/delay?' + urllib.parse.urlencode({
            'url': 'https://www.gstatic.com/generate_204', 'timeout': 3000})
        result = diagnostic_api(settings, config, path, timeout=4)
        ok = isinstance(result.get('delay'), (int, float)) and result['delay'] >= 0
        return {'ok': ok, 'stage': 'first_hop', 'delay_ms': result.get('delay') if ok else None}
    except (OSError, ValueError, KeyError, TypeError):
        return {'ok': False, 'stage': 'first_hop', 'detail': '指定第一跳访问独立测试站失败，包含节点/其DNS或测试站问题'}


def trace_webshare(settings, config, proxies, node, host):
    """Trace a bound physical DIRECT route or an API-verified first-hop route."""
    start = time.monotonic()
    deadline = start + 8
    stages, stream = {}, None
    stage = 'local_proxy'
    group = node.get('dialer-proxy')
    direct = not group or group == 'DIRECT'
    try:
        try:
            server = str(ipaddress.ip_address(node['server']))
        except ValueError:
            return {'ok': None, 'stage': 'unsupported', 'host': host,
                    'detail': 'Webshare地址不是IP，暂不支持分离地址解析与连接诊断'}
        def remaining():
            left = deadline - time.monotonic()
            if left <= 0:
                raise TimeoutError()
            return min(3, left)

        def send(data):
            stream.settimeout(remaining())
            stream.sendall(data)

        def receive(count):
            data = b''
            while len(data) < count:
                stream.settimeout(remaining())
                chunk = stream.recv(count - len(data))
                if not chunk:
                    raise ConnectionError()
                data += chunk
            return data

        def mark(name):
            stages[name] = round(time.monotonic() - start, 3)

        if direct:
            stage = 'direct_route_confirmation'
            interface = settings.get('direct_interface')
            node_interface = node.get('interface-name') or config.get('interface-name')
            if (not interface or interface == 'lo' or interface == config.get('tun', {}).get('device')
                    or (node_interface and node_interface != interface)):
                return {'ok': None, 'stage': stage, 'host': host,
                    'detail': '仅第二跳诊断需要与节点一致的已核对物理网卡，不发送代理凭据'}
            socket.if_nametoindex(interface)
            stream = socket.socket(socket.AF_INET6 if ':' in server else socket.AF_INET, socket.SOCK_STREAM)
            stream.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, interface.encode()+b'\0')
            if stream.getsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, 64).rstrip(b'\0') != interface.encode():
                return {'ok': None, 'stage': stage, 'host': host,
                    'detail': '物理网卡绑定未确认，不发送代理凭据'}
            stage = 'direct_to_webshare'
            stream.settimeout(remaining())
            stream.connect((server, int(node['port'])))
            mark(stage)
        else:
            url = urllib.parse.urlsplit(settings['proxy_url'])
            if url.scheme != 'http' or url.username or url.password:
                return {'ok': None, 'stage': 'unsupported', 'host': host, 'detail': '需无认证本机HTTP代理进行分段诊断'}
            expected_first = leaf(group, proxies)
            stream = socket.create_connection((url.hostname, url.port or 80), timeout=remaining())
            source_port = stream.getsockname()[1]
            mark('local_proxy')
            stage = 'first_to_webshare'
            authority = ('['+server+']' if ':' in server else server) + ':' + str(node['port'])
            send(('CONNECT '+authority+' HTTP/1.1\r\nHost: '+authority+'\r\n\r\n').encode())
            headers = b''
            while not headers.endswith(b'\r\n\r\n'):
                headers += receive(1)
                if len(headers) > 8192:
                    raise ValueError()
            if b' 200 ' not in headers.split(b'\r\n')[0]:
                raise ConnectionError()
            stage = 'route_confirmation'
            chains = []
            for attempt in range(4):
                connections = diagnostic_api(settings, config, '/connections', timeout=remaining())['connections']
                route = next((item for item in connections
                    if str(item.get('metadata', {}).get('sourcePort')) == str(source_port)), None)
                chains = route.get('chains', []) if route else []
                if chains:
                    break
                time.sleep(0.05)
            if expected_first not in chains or node['name'] in chains:
                return {'ok': None, 'stage': stage, 'host': host, 'elapsed': stages,
                    'detail': '诊断连接未确认沿同一第一跳，无法据此定位，不发送代理凭据'}
        stage = 'webshare_socks'
        send(b'\x05\x01\x02')
        if receive(2) != b'\x05\x02':
            return {'ok': False, 'stage': 'webshare_auth', 'host': host, 'elapsed': stages,
                    'detail': 'Webshare未接受用户名密码认证方式'}
        mark('webshare_socks')
        stage = 'webshare_auth'
        username = str(node['username']).encode()
        password = str(node['password']).encode()
        if len(username) > 255 or len(password) > 255:
            raise ValueError()
        send(bytes([1, len(username)]) + username + bytes([len(password)]) + password)
        if receive(2) != b'\x01\x00':
            return {'ok': False, 'stage': stage, 'host': host, 'elapsed': stages,
                    'detail': 'Webshare明确拒绝认证（账号/密码/账户授权需检查）'}
        mark(stage)
        stage = 'webshare_to_target'
        domain = host.encode('idna')
        send(b'\x05\x01\x00\x03' + bytes([len(domain)]) + domain + b'\x01\xbb')
        reply = receive(4)
        if reply[1] != 0:
            return {'ok': False, 'stage': stage, 'host': host, 'elapsed': stages,
                    'detail': 'Webshare连接目标失败（含远端DNS），SOCKS返回码 '+str(reply[1])}
        count = {1: 4, 4: 16}.get(reply[3])
        count = receive(1)[0] if reply[3] == 3 else count
        if count is None:
            raise ValueError()
        receive(count + 2)
        mark(stage)
        stage = 'target_tls'
        stream.settimeout(remaining())
        stream = ssl.create_default_context().wrap_socket(stream, server_hostname=host)
        mark(stage)
        stage = 'target_http'
        path = '/ip' if host == 'ifconfig.me' else '/'
        send(('GET '+path+' HTTP/1.1\r\nHost: '+host+'\r\nConnection: close\r\nUser-Agent: curl/8\r\n\r\n').encode())
        stream.settimeout(remaining())
        response = http.client.HTTPResponse(stream)
        response.begin()
        body = response.read(128).decode(errors='replace').strip()
        mark(stage)
        if response.status != 200:
            return {'ok': False, 'stage': stage, 'host': host, 'elapsed': stages,
                    'detail': '目标HTTP返回 '+str(response.status)}
        stage = 'exit_verification'
        if str(ipaddress.ip_address(body)) != str(ipaddress.ip_address(settings['expected_ip'])):
            return {'ok': False, 'stage': stage, 'host': host, 'elapsed': stages,
                    'detail': 'Webshare查询出口与预期IP不符'}
        return {'ok': True, 'stage': 'complete', 'host': host, 'elapsed': stages}
    except (OSError, ValueError, KeyError, TypeError, http.client.HTTPException) as error:
        # Do not expose exception strings: they may include credentials or internal endpoints.
        return {'ok': False, 'stage': stage, 'host': host, 'elapsed': stages,
                'error_type': type(error).__name__}
    finally:
        if stream:
            stream.close()


def summarize_diagnostics(first, traces):
    names = {'local_proxy': '服务器→本地Clash连接失败',
        'first_to_webshare': '连接Webshare未完成（尚未核对实际第一跳路径）',
        'direct_route_confirmation': '仅第二跳物理网卡绑定失败或无法确认',
        'direct_to_webshare': '服务器直连Webshare的TCP建连失败',
        'webshare_socks': 'Webshare的SOCKS握手未完成',
        'webshare_auth': 'Webshare代理认证失败或无响应',
        'webshare_to_target': 'Webshare→目标网站连接失败（包含远端DNS）',
        'target_tls': '目标网站TLS握手失败', 'target_http': '目标网站HTTP请求失败',
        'exit_verification': '目标返回的出口IP无效或不符'}
    lines = []
    if first.get('ok') is True:
        lines.append('第一跳独立探测：通过。')
    elif first.get('ok') is False:
        lines.append('第一跳独立探测：失败；可能是服务器到节点、节点出站/DNS或独立测试站，不能仅凭此确定物理故障位置。')
    else:
        lines.append('第一跳独立探测：不适用或无法确认。')
    for trace in traces:
        if trace.get('ok') is True:
            lines.append(trace['host']+'：分段重测通过（SOCKS、认证、目标连接、TLS、HTTP及出口）。')
        elif trace.get('ok') is None:
            lines.append(trace['host']+'：'+trace.get('detail', '无法确认诊断路径')+'。')
        else:
            lines.append(trace['host']+'：'+names.get(trace.get('stage'), '无法定位')
                +'；'+trace.get('detail', trace.get('error_type', '未知原因'))+'。')
    if traces and all(item.get('ok') is True for item in traces):
        lines.append('故障后重测已通过：原失败可能为瞬时异常或主探测路径差异，本次结果不能追溯确定原故障段；由下一轮正式检测决定恢复。')
    return '\n'.join(lines)


def collect_diagnostics(settings):
    try:
        config = yaml.safe_load(Path(settings['mihomo_config']).read_text())
        proxies = diagnostic_api(settings, config, '/proxies')['proxies']
        runtime = diagnostic_api(settings, config, '/configs')
        rules = diagnostic_api(settings, config, '/rules')['rules']
        candidates = {p['name'] for p in config.get('proxies', [])
            if p.get('type') == 'socks5' and p.get('server') == settings['webshare_server']}
        if not route_uses_webshare(str(runtime.get('mode', '')).lower(), proxies, rules,
                candidates, settings['probe_host']):
            return {'summary': '配置/模式问题：当前未确认使用Webshare第二跳（含只走第一跳）；不能据此判定物理网络断开。'}
        selected_name = leaf('GLOBAL', proxies) if str(runtime.get('mode', '')).lower() == 'global' else None
        if selected_name not in candidates:
            for rule in rules:
                if route_uses_webshare('rule', proxies, [rule], candidates, settings['probe_host']):
                    selected_name = leaf(rule.get('proxy'), proxies)
                    break
        node = next(p for p in config.get('proxies', []) if p.get('name') == selected_name)
        group = node.get('dialer-proxy')
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            first = pool.submit(first_hop_probe, settings, config, proxies, group) if group and group != 'DIRECT' else None
            jobs = [pool.submit(trace_webshare, settings, config, proxies, node, host)
                    for host in ('ifconfig.me', 'api.ipify.org')]
            first_result = first.result() if first else {'ok': None, 'stage': 'first_hop'}
            traces = [job.result() for job in jobs]
        return {'summary': summarize_diagnostics(first_result, traces),
                'first_hop': first_result, 'traces': traces}
    except (OSError, ValueError, KeyError, TypeError, StopIteration, yaml.YAMLError):
        return {'summary': '诊断无法读取Clash管理API或Webshare配置；请检查本机Clash服务/配置，尚不能判断远端链路。'}


def diagnose(settings):
    try:
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()),
            '--config', settings.get('_config_path', '/etc/claude-webshare-watch/config.json'),
            '--diagnose-only'], capture_output=True, text=True, timeout=18)
        if result.returncode == 0:
            return json.loads(result.stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    return {'summary': '分段诊断超时或失败，无法确认具体链路；原有故障拦截保持生效。'}



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
    now = time.time()
    probe_healthy = healthy
    # Old incidents were immediately announced; preserve their recovery semantics.
    if previous.get('incident') and 'alert_queued' not in previous:
        previous.update(alert_queued=True, failure_started_at=previous.get('checked_at', now))
    state = dict(previous, checked_at=now, probe_healthy=probe_healthy, reason=reason)
    successes = previous.get('recovery_successes', 0) + 1 if probe_healthy else 0
    state['recovery_successes'] = successes
    if previous.get('incident') and probe_healthy:
        healthy = successes >= max(1, int(settings.get('recovery_successes', 2)))
        if not healthy:
            state['reason'] = '第二跳探测通过，等待连续成功确认；启动拦截仍保持'
    state['healthy'] = healthy
    # Publish effective recovery before unloading: guard must not kill newly allowed tasks.
    if healthy:
        atomic_json(path, state)
    try:
        set_gate(settings, not healthy)
        state.pop('gate_error', None)
        state['gate_blocked'] = not healthy
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        healthy = probe_healthy = False
        reason = '启动门禁更新失败；持续终止 Claude，需管理员检查 AppArmor'
        state.update(healthy=False, probe_healthy=False, recovery_successes=0,
                     reason=reason, gate_error=True)
    action = decision(previous, healthy)
    alerts = state.pop('pending_alerts', [])
    legacy = state.pop('pending_alert', None)
    if legacy:
        alerts.append(legacy)
    if action == 'healthy':
        state['incident'] = False
        if previous.get('incident') and previous.get('alert_queued'):
            # A queued failure stays ahead of its recovery even if delivery was unavailable.
            alerts.append({
                'id': str(previous.get('incident_id', time.time_ns())) + '-recovered',
                'text': 'Claude 网络第二跳已恢复：连续成功确认 Webshare 出口，启动拦截已解除。'
                    '现在可以运行新的 Claude CLI 任务；此前停止的任务不会自动重启。'})
        for key in ('failure_started_at', 'alert_queued', 'incident_text', 'diagnostics'):
            state.pop(key, None)
    else:
        targets = snapshot()
        killed, failed = kill_snapshot(targets)
        state.update(last_killed=killed, kill_failed=failed)
    if action == 'incident':
        incident_id = str(time.time_ns())
        state.update(incident=True, incident_id=incident_id, killed=killed, kill_failed=failed,
                     failure_started_at=now, alert_queued=False)
        state.pop('diagnostics', None)
        state['incident_text'] = (
            'Claude 网络第二跳检测失败：'+reason+'。首次失败时已停止 Claude CLI 及子进程 '
            +str(len(killed))+' 个；停止失败 '+str(len(failed))+' 个。'
            +('启动门禁异常，正在持续清理新进程；请检查 AppArmor。' if state.get('gate_error')
              else '已启用故障期间启动拦截，连续成功确认恢复后才解除；不会自动重启旧任务。'))
    state['pending_alerts'] = alerts
    atomic_json(path, state)
    if (not healthy and not probe_healthy and not state.get('alert_queued')
            and now - state['failure_started_at'] >= max(0, float(settings.get('alert_delay_seconds', 90)))):
        # Protection already applied; diagnostics and outward alerts are delayed independently.
        state['diagnostics'] = dict(diagnose(settings), collected_at=time.time())
        alerts.append({
            'id': state['incident_id'],
            'text': state['incident_text'] + '\n故障尚未恢复，最新检测：' + reason
                + '\n分段诊断（故障后重测）：\n' + state['diagnostics']['summary']})
        state['alert_queued'] = True
        atomic_json(path, state)
    # One delivery per run bounds notification time; preserve chronological events.
    if alerts:
        alert = alerts[0]
        state['notification_sent'] = notify(settings, alert['text'], alert['id'])
        if state['notification_sent']:
            alerts.pop(0)
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
    parser.add_argument('--diagnose-only', action='store_true', help='read-only staged diagnostics; no gate, state, kill or notification')
    args = parser.parse_args()
    settings = json.loads(Path(args.config).read_text())
    settings['_config_path'] = args.config
    if args.diagnose_only:
        print(json.dumps(collect_diagnostics(settings), ensure_ascii=False))
        return 0
    if args.guard:
        return guard(settings)
    lock = Path(settings['state_path']).with_suffix('.lock')
    lock.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with lock.open('w') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return run(settings, args.probe_only)


if __name__ == '__main__':
    raise SystemExit(main())
