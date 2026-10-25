#!/usr/bin/python3
import pathlib,subprocess,json,yaml,secrets,sys,os
root=pathlib.Path('/home/serveruser/.config/mihomo/tx')
mode=sys.argv[1]; out=pathlib.Path(sys.argv[2])
c=yaml.safe_load((root/'base.yaml').read_text())
if mode not in ('proxy','tun','tun-nodns'): raise SystemExit('bad mode')
c['tun']={'enable':mode!='proxy','device':'mihomo-tx','stack':'mixed','auto-route':True,'auto-redirect':True,'auto-detect-interface':True,'strict-route':True,'mtu':1500,'inet6-address':['fdfe:dcba:9876::1/126'],'iproute2-table-index':20220,'iproute2-rule-index':19000,'route-exclude-address':['10.0.0.0/22','172.17.0.0/16','172.18.0.0/16','169.254.0.0/16']}
r=subprocess.run(['node',str(root/'apply-extension.cjs'),str(root/'webshare-dns.js')],input=json.dumps(c),text=True,capture_output=True,timeout=10)
if r.returncode: raise SystemExit(r.stderr)
c=json.loads(r.stdout)
c.update({'mixed-port':17890 if mode=='proxy' else 7890,'external-controller':'127.0.0.1:19090','secret':secrets.token_urlsafe(32),'allow-lan':False,'bind-address':'127.0.0.1','mode':'rule','ipv6':True,'find-process-mode':'strict'})
c['dns']['listen']='127.0.0.1:15353' if mode=='proxy' else '127.0.0.1:53'
for k,v in c['dns']['nameserver-policy'].items():
 values=v if isinstance(v,list) else [v]
 c['dns']['nameserver-policy'][k]=[x for val in values for x in (['183.60.83.19','183.60.82.98'] if val=='system' else [val])]
if mode=='tun-nodns': c['tun']['dns-hijack']=[]
# Explicit process/domain exceptions; do not exempt every root process.
extra=['PROCESS-NAME,apt,DIRECT','PROCESS-NAME,apt-get,DIRECT','PROCESS-NAME,unattended-upgrade,DIRECT','DOMAIN-SUFFIX,tencentyun.com,DIRECT']
private_dns=['tcp://183.60.83.19:53#eth0','tcp://183.60.82.98:53#eth0']
policy={'+.tencentyun.com':private_dns}
c['dns'].setdefault('fake-ip-filter',[]).append('+.tencentyun.com')
# Only actual system repository domains are added, excluding arbitrary URLs.
domains=set()
import re
for p in list(pathlib.Path('/etc/apt').glob('sources.list'))+list(pathlib.Path('/etc/apt/sources.list.d').glob('*')):
 if p.is_file():
  text='\n'.join(line for line in p.read_text().splitlines() if not line.lstrip().startswith('#'))
  domains.update(re.findall(r'https?://([^/\s:]+)',text))
for d in sorted(domains):
 if d in ('ipv4.webshare.io','ifconfig.me','ipinfo.io'): raise SystemExit('exception conflict')
 extra.append('DOMAIN,'+d+',DIRECT')
 policy[d]=private_dns if d=='tencentyun.com' or d.endswith('.tencentyun.com') else ['https://223.5.5.5/dns-query#DIRECT','https://223.6.6.6/dns-query#DIRECT']
 c['dns'].setdefault('fake-ip-filter',[]).append(d)
# Mihomo v1.19.31 resolves the first matching policy, including rule-set keys.
c['dns']['nameserver-policy']={**policy,**{k:v for k,v in c['dns']['nameserver-policy'].items() if k not in policy}}
c['rules']=extra+c['rules']
c.pop('tx-adapter',None)
# Preserve rule-cache naming used by the original subscription.
out.parent.mkdir(parents=True,exist_ok=True)
fd=os.open(str(out),os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
with os.fdopen(fd,'w') as f: yaml.safe_dump(c,f,allow_unicode=True,sort_keys=False)
print('generated',mode,'rules',len(c['rules']),'system_domains',sorted(domains))
