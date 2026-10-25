#!/usr/bin/env python3
"""Validate subscription shape; optionally produce a LOCAL-ONLY stable preview.

No source or service is modified. --stable-out must be a new path.
"""
import argparse
import os
import re
from pathlib import Path
import yaml

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('file', type=Path)
p.add_argument('--js', type=Path, required=True)
p.add_argument('--stable', action='store_true', help='check stable listener constraints')
p.add_argument('--stable-out', type=Path, help='write sanitized stable preview, never install it')
a = p.parse_args()
try:
    c = yaml.safe_load(a.file.read_text())
except (OSError, yaml.YAMLError):
    raise SystemExit('无法读取或解析 YAML；为保护凭据不输出原文，请在本机核对语法')
if not isinstance(c, dict):
    raise SystemExit('配置必须是完整的 YAML 映射')
m = re.search(r'FIRST_HOP_GROUP\s*=\s*([\x27\x22])(.*?)\1', a.js.read_text())
if not m:
    raise SystemExit('无法确定 JS 的 FIRST_HOP_GROUP，需人工核对')
groups = c.get('proxy-groups', [])
if not isinstance(groups, list) or not all(isinstance(g, dict) for g in groups):
    raise SystemExit('proxy-groups 格式错误')
errors = []
if m.group(2) not in {g.get('name') for g in groups}:
    errors.append('缺少 JS 指定的第一跳代理组')
providers = c.get('rule-providers', {})
if not isinstance(providers, dict):
    raise SystemExit('rule-providers 格式错误')
missing = {'private_domain', 'cn_domain', 'geolocation-!cn', 'cn_ip'} - set(providers)
if missing:
    errors.append('缺少现有脚本依赖的规则集：' + ', '.join(sorted(missing)))
if not c.get('proxies') and not c.get('proxy-providers'):
    errors.append('既无节点，也无代理提供器')
if not isinstance(c.get('rules'), list) or not c['rules']:
    errors.append('缺少完整分流规则')
if not a.stable_out and not a.stable:
    if any(c.get(k) for k in ('port', 'socks-port', 'redir-port', 'tproxy-port',
                              'listeners', 'external-controller-tls',
                              'external-controller-unix')):
        errors.append('原订阅有生成器未覆盖的额外入口，请先审查并清除暂存副本中的入口')
if a.stable_out:
    c.update({'mixed-port': 7890, 'allow-lan': False, 'bind-address': '127.0.0.1'})
    # Stable service has no TUN capabilities or DNS port-53 privilege.
    c['tun'] = {'enable': False}
    c['dns'] = {'enable': False}
    for key in ('port', 'socks-port', 'redir-port', 'tproxy-port', 'listeners',
                'external-controller', 'external-controller-tls',
                'external-controller-unix', 'external-ui', 'external-ui-url',
                'external-ui-name', 'secret'):
        c.pop(key, None)
if a.stable or a.stable_out:
    if c.get('allow-lan') is not False or c.get('bind-address') != '127.0.0.1':
        errors.append('稳定配置必须只监听 127.0.0.1，allow-lan=false')
    if c.get('mixed-port') != 7890:
        errors.append('稳定配置 mixed-port 必须是 7890')
    if c.get('tun', {}).get('enable') or c.get('dns', {}).get('enable'):
        errors.append('本工具生成的稳定配置必须关闭 TUN 与内置 DNS')
    if any(c.get(k) for k in ('port', 'socks-port', 'redir-port', 'tproxy-port',
                              'listeners', 'external-controller',
                              'external-controller-tls', 'external-controller-unix')):
        errors.append('稳定配置包含额外监听入口，需人工核对')
for error in errors:
    print('ERROR:', error)
if errors:
    raise SystemExit(1)
if a.stable_out:
    fd = os.open(a.stable_out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as f:
        yaml.safe_dump(c, f, allow_unicode=True, sort_keys=False)
print('BASE_CHECK_OK; nodes=', len(c.get('proxies', [])), 'groups=', len(groups))
