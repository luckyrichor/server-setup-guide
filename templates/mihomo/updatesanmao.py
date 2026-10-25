#!/usr/bin/env python3
# Server path: /home/serveruser/.config/mihomo/tx/updatesanmao.py
import fcntl, hashlib, json, os, subprocess, sys, tempfile, copy, re
from pathlib import Path
import yaml
ROOT = Path.home() / '.config/mihomo/tx'

def validate(path):
    c = yaml.safe_load(path.read_text(encoding='utf-8'))
    if not isinstance(c, dict):
        raise ValueError('订阅不是完整 YAML 配置')
    groups = c.get('proxy-groups', [])
    if not isinstance(groups, list) or '机场第一跳' not in {g.get('name') for g in groups if isinstance(g, dict)}:
        raise ValueError('缺少机场第一跳代理组')
    missing = {'private_domain', 'cn_domain', 'geolocation-!cn', 'cn_ip'} - set(c.get('rule-providers') or {})
    if missing:
        raise ValueError('缺少所需规则集')
    if not c.get('proxies') and not c.get('proxy-providers'):
        raise ValueError('没有代理节点或节点提供器')
    if not isinstance(c.get('rules'), list) or not c['rules']:
        raise ValueError('没有分流规则')
    return c

# Comparison only: never rewrite the downloaded YAML or remove actual nodes.
_STAT_LABEL = re.compile(
    r'^(剩余流量|已用流量|总流量|距离下次重置剩余|重置倒计时|套餐到期|到期时间|订阅到期|有效期至)\s*[:：]\s*.+$'
)

def comparison_config(config):
    result = copy.deepcopy(config)
    labels = {}
    for index, node in enumerate(result.get('proxies') or []):
        if not isinstance(node, dict):
            continue
        name = node.get('name')
        match = _STAT_LABEL.fullmatch(name) if isinstance(name, str) else None
        if match:
            # A tuple is an unambiguous comparison marker, never a real node name.
            marker = ('subscription-stat-label', index, match.group(1))
            labels[name] = marker
            node['name'] = marker
    def reference(value):
        return labels.get(value, value) if isinstance(value, str) else value
    for node in result.get('proxies') or []:
        if isinstance(node, dict) and 'dialer-proxy' in node:
            node['dialer-proxy'] = reference(node['dialer-proxy'])
    for group in result.get('proxy-groups') or []:
        if isinstance(group, dict) and isinstance(group.get('proxies'), list):
            group['proxies'] = [reference(value) for value in group['proxies']]
    def rules(values):
        if not isinstance(values, list):
            return values
        out = []
        for value in values:
            if isinstance(value, str) and ',' in value:
                prefix, target = value.rsplit(',', 1)
                if target in labels:
                    value = (prefix, labels[target])
            out.append(value)
        return out
    if 'rules' in result:
        result['rules'] = rules(result['rules'])
    for key, values in (result.get('sub-rules') or {}).items():
        result['sub-rules'][key] = rules(values)
    def dns_references(value):
        if isinstance(value, list):
            return [dns_references(item) for item in value]
        if isinstance(value, dict):
            return {key: dns_references(item) for key, item in value.items()}
        if isinstance(value, str) and '#' in value:
            prefix, target = value.rsplit('#', 1)
            if target in labels:
                return (prefix, labels[target])
        return value
    if isinstance(result.get('dns'), dict):
        result['dns'] = dns_references(result['dns'])
    return result

def unchanged_subscription(new_config, old_path):
    try:
        old_config = validate(old_path)
    except (ValueError, OSError, yaml.YAMLError):
        return False
    return comparison_config(new_config) == comparison_config(old_config)


def main():
    os.umask(0o077)
    with (ROOT / '.subscription-download.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('另一个订阅下载正在进行，请稍后重试')
        url = (ROOT / 'subscription.url').read_text().strip()
        if not url.startswith('https://') or any(ord(ch) < 32 for ch in url):
            raise ValueError('订阅地址必须是 HTTPS')
        fd, name = tempfile.mkstemp(prefix='.subscription-', suffix='.yaml', dir=ROOT)
        os.close(fd)
        temp = Path(name)
        try:
            # Keep the private subscription URL out of process arguments and error output.
            r = subprocess.run(['curl', '--config', '-', '--fail', '--silent', '--location',
                '--proto', '=https', '--proto-redir', '=https', '--connect-timeout', '10',
                '--max-time', '60', '--max-filesize', '10485760', '--user-agent', 'clash.meta',
                '--proxy', 'http://127.0.0.1:7890', '--noproxy', '', '--output', str(temp)],
                input='url = '+json.dumps(url)+'\n', text=True, capture_output=True, timeout=65)
            if r.returncode:
                raise ValueError(f'订阅下载失败（curl 返回码 {r.returncode}），旧文件保留')
            c = validate(temp)
            target = ROOT / 'base.upload.yaml'
            # Compare parsed configuration, ignoring only recognized statistics labels and their references.
            # Identical pending content does not imply that it has already been published.
            if target.is_file() and unchanged_subscription(c, target):
                print('✅ 第一跳机场订阅没有变化（已忽略流量等统计信息），未替换文件。')
                return
            os.replace(temp, target)
            print(f'✅ 第一跳机场订阅下载完成，请用助手使其生效，节点数：{len(c.get("proxies") or [])}')
            print(f'待发布文件：{target}')
        finally:
            temp.unlink(missing_ok=True)

if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, yaml.YAMLError, subprocess.TimeoutExpired):
        print('❌ 第一跳机场订阅下载或检查失败，原文件已保留，当前配置未改变。', file=sys.stderr)
        sys.exit(1)
