#!/usr/bin/python3
import os,sys,json,pathlib,subprocess,time,fcntl,hashlib
R=pathlib.Path('/run/mihomo-tx'); R.mkdir(mode=0o700,exist_ok=True)
STATE=R/'state.json'; LOCK=R/'control.lock'; UNIT='mihomo-tx-candidate.service'
DROP=pathlib.Path('/run/systemd/network/10-netplan-eth0.network.d/90-mihomo-tx-dns.conf')
POLICY=pathlib.Path('/run/systemd/networkd.conf.d/90-mihomo-tx.conf')
DEP=pathlib.Path('/var/lib/mihomo-tx/deployment.json')
DEADLINE=None
def run(args,timeout=8,check=False):
 if DEADLINE is not None:
  timeout=min(timeout,DEADLINE-time.monotonic())
  if timeout<=0:raise RuntimeError('cleanup total deadline exceeded')
 p=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
 if check and p.returncode: raise RuntimeError(' '.join(args)+': '+p.stderr.strip())
 return p

def state():
 return json.loads(STATE.read_text()) if STATE.exists() else {'phase':'prepared','dns':False}
def save(s):
 warning=pathlib.Path('/run/mihomo-tx-warning')
 if s.get('phase') in ('failed','recovering'):
  warning.write_text('警告：TX 代理处于 '+s['phase']+' 状态。请运行 sudo /usr/local/libexec/mihomo-tx-control status 检查。\n');warning.chmod(0o644)
 else:warning.unlink(missing_ok=True)
 t=R/'state.tmp'; t.write_text(json.dumps(s));t.chmod(0o600);os.replace(t,STATE)

def deploysave(d):
 t=DEP.with_suffix('.tmp');t.write_text(json.dumps(d));t.chmod(0o600);os.replace(t,DEP)
def bootid():return pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()

def dnsneedsrestore(s):
 actual=run(['resolvectl','dns','eth0'],check=True).stdout
 return bool(s.get('dns') or DROP.exists() or '127.0.0.1' in actual or '198.18.' in actual)

def verifydns_once():
 actual=run(['resolvectl','dns','eth0'],check=True).stdout
 if any(x in actual for x in ('127.0.0.1','198.18.')) or not any(x in actual for x in ('183.60.83.19','183.60.82.98')):
  raise RuntimeError('DNS recovery unverified: '+actual.strip())
 p=run(['getent','ahostsv4','www.baidu.com'],timeout=5,check=True)
 if not p.stdout.strip() or '198.18.' in p.stdout:raise RuntimeError('system resolution recovery failed')

def verifydns():
 end=time.monotonic()+10
 while True:
  try:verifydns_once();return
  except RuntimeError:
   if time.monotonic()>=end:raise
   time.sleep(.5)

def waitnetwork(expected):
 end=time.monotonic()+10
 while True:
  configured='(configured)' in run(['networkctl','status','eth0','--no-pager'],timeout=2,check=True).stdout
  actual=run(['resolvectl','dns','eth0'],timeout=2,check=True).stdout
  if configured and expected in actual:return
  if time.monotonic()>=end:raise RuntimeError('networkd configuration did not settle')
  time.sleep(.5)

def captureipv6():
 addresses=json.loads(run(['ip','-6','-j','addr','show','dev','eth0'],check=True).stdout)
 static=[a for link in addresses for a in link.get('addr_info',[]) if a.get('scope')=='global' and not a.get('dynamic')]
 routes=json.loads(run(['ip','-6','-j','route','show','default'],check=True).stdout)
 return {'addresses':static,'routes':routes}

def restoreipv6(s):
 for a in s.get('prior_ipv6',{}).get('addresses',[]):
  run(['ip','-6','addr','replace',a['local']+'/'+str(a['prefixlen']),'dev','eth0'],check=True)
 for r in s.get('prior_ipv6',{}).get('routes',[]):
  if r.get('gateway') and r.get('dev')=='eth0':
   run(['ip','-6','route','replace','default','via',r['gateway'],'dev','eth0','metric',str(r.get('metric',1024))],check=True)
class locked:
 def __enter__(self):
  self.f=open(LOCK,'a');self.fchmod=os.fchmod(self.f.fileno(),0o600);end=time.monotonic()+10
  while True:
   try:fcntl.flock(self.f,fcntl.LOCK_EX|fcntl.LOCK_NB);return
   except BlockingIOError:
    if time.monotonic()>end:raise RuntimeError('lock deadline')
    time.sleep(.1)
 def __exit__(self,*a):self.f.close()

def guardports():
 d=json.loads(DEP.read_text()) if DEP.exists() else {}
 ports=d.get('guard_tcp_ports',[22,80,443])
 if not ports or len(ports)>32 or len(set(ports))!=len(ports) or any(type(p)!=int or not 1<=p<=65535 for p in ports):raise RuntimeError('invalid guard_tcp_ports')
 return ports

def kernelcheck():
 d=json.loads(DEP.read_text())
 expected=d.get('kernel_version','v1.19.31')
 actual=run(['/usr/local/bin/mihomo','-v'],check=True).stdout
 if expected not in actual.split():raise RuntimeError('kernel version changed; verify routing cleanup before enabling TUN')

def guardup():
 with locked():
  kernelcheck()
  s=state()
  if s['phase'] in ['recovering','failed','stable']:raise RuntimeError('recovery blocks candidate startup')
  s['prior_ipv6']=captureipv6()
  if DEP.exists():
   d=json.loads(DEP.read_text())
   if not d.get('enabled'):raise RuntimeError('deployment recovery blocks startup')
   if hashlib.sha256((DEP.parent/'active/config.yaml').read_bytes()).hexdigest()!=d['version']:raise RuntimeError('deployment config hash mismatch')
   if not s['prior_ipv6']['addresses']:s['prior_ipv6']=d['prior_ipv6']
   s['version']=d['version'];s['boot_id']=bootid()
  save(s)
  if POLICY.exists() and not s.get('networkd_policy'):raise RuntimeError('networkd policy ownership conflict')
  if not POLICY.exists():
   POLICY.parent.mkdir(parents=True,exist_ok=True)
   POLICY.write_text('[Network]\nManageForeignRoutingPolicyRules=no\nManageForeignRoutes=no\n')
   POLICY.chmod(0o644);s['networkd_policy']=True;save(s)
   run(['systemctl','restart','systemd-networkd'],timeout=12,check=True)
   restoreipv6(s)
  # Use six reserved priorities; compare full existing rule before reuse.
  for family in ['-4','-6']:
   rules=json.loads(run(['ip',family,'-j','rule','show'],check=True).stdout)
   for i,port in enumerate(guardports()):
    pref=18000+i;found=[r for r in rules if r.get('priority')==pref]
    if found and not all(str(r.get('sport'))==str(port) and r.get('table')=='main' for r in found):raise RuntimeError('guard priority conflict')
    if not found:run(['ip',family,'rule','add','pref',str(pref),'ipproto','tcp','sport',str(port),'lookup','main','protocol','kernel'],check=True)
  s['guard_tcp_ports']=guardports();s['phase']='starting';save(s)

def tunremove():
 # Names and IDs were observed in the isolated TX v1.19.31 instance.
 errors=[]
 for args in [['nft','delete','table','inet','mihomo']]:
  p=run(args)
  if p.returncode and 'No such file' not in p.stderr:errors.append(p.stderr)
 for family in ['-4','-6']:
  rules=json.loads(run(['ip',family,'-j','rule']).stdout)
  for r in rules:
   if 19000<=r.get('priority',-1)<=19010:
    p=run(['ip',family,'rule','del','pref',str(r['priority'])]);
    if p.returncode:errors.append(p.stderr)
  run(['ip',family,'route','flush','table','20220'])
 p=run(['ip','link','show','mihomo-tx'])
 if p.returncode==0:run(['ip','link','delete','mihomo-tx'],check=True)
 for family in ['-4','-6']:
  if any(19000<=r.get('priority',-1)<=19010 for r in json.loads(run(['ip',family,'-j','rule']).stdout)):errors.append('route rule residual')
  if run(['ip',family,'route','show','table','20220']).stdout.strip():errors.append('routing table 20220 residual')
 if run(['nft','list','table','inet','mihomo']).returncode==0:errors.append('nft residual')
 return errors

def cleanup():
 global DEADLINE
 start=time.monotonic();DEADLINE=start+75;errors=[]
 with locked():
  if run(['systemctl','show',UNIT,'-p','MainPID','--value']).stdout.strip() not in ('','0'):raise RuntimeError('candidate process not gone')
  s=state();s['phase']='recovering';save(s)
  for attempt in range(3):
   try:errors=tunremove()
   except Exception as e:errors=[str(e)]
   if not errors:break
   if attempt<2:time.sleep(2)
  if errors and time.monotonic()<start+50:
   try:errors=tunremove()
   except Exception as e:errors=[str(e)]
  if not errors:
   needs=dnsneedsrestore(s)
   if DROP.exists():DROP.unlink()
   if POLICY.exists() and s.get('networkd_policy'):
    POLICY.unlink();needs=True
    try:run(['systemctl','restart','systemd-networkd'],timeout=12,check=True)
    except Exception as e:errors.append(str(e))
   if needs:
    for args in [['networkctl','reload'],['resolvectl','revert','eth0'],['networkctl','reconfigure','eth0'],['resolvectl','flush-caches']]:
     try:
      p=run(args,timeout=5)
      if p.returncode:errors.append(p.stderr)
     except Exception as e:errors.append(str(e))
    try:restoreipv6(s)
    except Exception as e:errors.append(str(e))
   try:verifydns()
   except Exception as e:errors.append(str(e))
   if not errors:s['dns']=False
   # Keep guard on any unresolved cleanup error.
   if not errors:
    for family in ['-4','-6']:
     for i in range(len(s.get('guard_tcp_ports',[22,80,443]))):run(['ip',family,'rule','del','pref',str(18000+i)])
  s['phase']='failed' if errors else 'stable';s['cleanup_errors']=errors;s['cleanup_seconds']=round(time.monotonic()-start,2);save(s)
  print(json.dumps({'cleanup_seconds':s['cleanup_seconds'],'errors':errors}))
  if errors:raise RuntimeError('incomplete recovery; guard retained')

def dnsup(port='53'):
 with locked():
  s=state()
  if s.get('skip_dns'):
   s['phase']='active-nodns';save(s);return
  if s['phase']=='recovering':raise RuntimeError('recovery in progress')
  if port not in ('53','15353'):raise RuntimeError('invalid DNS port')
  ready=False
  for i in range(5):
   p=run(['dig','@127.0.0.1','-p',port,'ipinfo.io','+time=1','+tries=1','+short'],timeout=2)
   if p.returncode==0 and p.stdout.strip():ready=True;break
   time.sleep(1)
  if not ready:raise RuntimeError('DNS readiness failure')
  if not s.get('prior_ipv6'):s['prior_ipv6']=captureipv6()
  DROP.parent.mkdir(parents=True,exist_ok=True)
  DROP.write_text('[Network]\nDNS=\nDNS=127.0.0.1:'+port+'\nDomains=\nDomains=~.\nDNSDefaultRoute=yes\n[DHCPv4]\nUseDNS=no\nUseDomains=no\n[DHCPv6]\nUseDNS=no\nUseDomains=no\n[IPv6AcceptRA]\nUseDNS=no\nUseDomains=no\n')
  with DROP.open('a') as f:
   for a in s['prior_ipv6']['addresses']:
    f.write('[Address]\nAddress='+a['local']+'/'+str(a['prefixlen'])+'\n')
   for r in s['prior_ipv6']['routes']:
    if r.get('gateway') and r.get('dev')=='eth0':
     f.write('[Route]\nDestination=::/0\nGateway='+r['gateway']+'\nGatewayOnLink=yes\nMetric='+str(r.get('metric',1024))+'\n')
  DROP.chmod(0o644);s['dns']=True;save(s)
  run(['networkctl','reload'],timeout=5,check=True)
  run(['networkctl','reconfigure','eth0'],timeout=5,check=True)
  waitnetwork('127.0.0.1' if port=='53' else '127.0.0.1:'+port)
  run(['resolvectl','dns','eth0','127.0.0.1:'+port],check=True)
  run(['resolvectl','domain','eth0','~.'],check=True)
  run(['resolvectl','flush-caches'])
  s['phase']='active';s['dns_port']=port;save(s)

def rollback(force=False):
 global DEADLINE
 with locked():
  s=state();s['phase']='recovering';save(s)
  if DEP.exists():
   d=json.loads(DEP.read_text());d['enabled']=False;deploysave(d)
 # Never hold shared lock while stopping a service whose cleanup takes that lock.
 if DEP.exists():
  run(['systemctl','disable','mihomo-tx-candidate.service','mihomo-tx-health.timer','mihomo-tx-boot-confirm.timer'],check=True)
  run(['systemctl','stop','mihomo-tx-health.timer','mihomo-tx-boot-confirm.timer'])
  run(['systemctl','enable','mihomo.service'],check=True)
 if force:run(['systemctl','kill','--kill-whom=all','--signal=SIGKILL',UNIT],timeout=5)
 run(['systemctl','stop',UNIT],timeout=135)
 cleanup()
 DEADLINE=None
 run(['systemctl','start','mihomo.service'],timeout=20,check=True)
 verifydns()
 end=time.monotonic()+15
 while True:
  p=run(['curl','--max-time','3','-x','http://127.0.0.1:7890','-fsS','-o','/dev/null','https://www.google.com/generate_204'],timeout=4)
  if p.returncode==0:break
  if time.monotonic()>=end:raise RuntimeError('stable proxy readiness failed: '+p.stderr.strip())
  time.sleep(.5)
 print('STABLE_SERVICE_AND_DNS_VERIFIED')

def stopped():
 cleanup()
 if os.environ.get('SERVICE_RESULT','success')!='success':
  with locked():
   s=state();s['phase']='recovering';save(s)
  # Queue recovery without waiting for this service's stop job to finish.
  run(['systemd-run','--collect','--unit=tx-mihomo-crash-recovery','/usr/local/libexec/mihomo-tx-control','rollback'],check=True)

def bootcheck():
 with locked():
  if not DEP.exists():return
  d=json.loads(DEP.read_text())
  if not d.get('enabled') or bootid()==d['origin_boot_id']:return
  confirmed=d.get('confirmed_version')==d['version']
 if confirmed:
  health()
  if state().get('phase')=='active':print('CONFIRMED_VERSION_BOOT_HEALTHY');return
 rollback()

def confirm():
 health()
 with locked():
  s=state();d=json.loads(DEP.read_text())
  if s['phase']!='active' or not d.get('enabled') or bootid()==d['origin_boot_id']:raise RuntimeError('new boot is not ready for confirmation')
  if s.get('version')!=d['version'] or s.get('boot_id')!=bootid():raise RuntimeError('confirmation version/boot mismatch')
  d['confirmed_version']=d['version'];d['confirmed_boot_id']=bootid();deploysave(d)
 print('FIRST_BOOT_CONFIRMED')

def prepare(nodns=False):
 with locked():
  if run(['systemctl','show',UNIT,'-p','MainPID','--value'],check=True).stdout.strip() not in ('','0'):raise RuntimeError('stop candidate before prepare')
  if DROP.exists() or POLICY.exists():raise RuntimeError('cleanup runtime network configuration before prepare')
  save({'phase':'prepared','dns':False,'skip_dns':nodns})

def status():
 s=state();d=json.loads(DEP.read_text()) if DEP.exists() else {}
 print(json.dumps({'phase':s.get('phase'),'enabled':d.get('enabled'),'version':d.get('version'),'guard_tcp_ports':d.get('guard_tcp_ports',[22,80,443]),'kernel_version':d.get('kernel_version','v1.19.31'),'cleanup_errors':s.get('cleanup_errors',[]),'candidate':run(['systemctl','is-active',UNIT]).stdout.strip(),'stable':run(['systemctl','is-active','mihomo']).stdout.strip(),'dns':run(['resolvectl','dns','eth0']).stdout.strip()},ensure_ascii=False,indent=2))

def armrestore():
 if run(['systemctl','is-active','tx-mihomo-activation-rollback.service']).stdout.strip() in ('active','activating'):raise RuntimeError('rollback is running')
 run(['systemctl','stop','tx-mihomo-activation-rollback.timer'],check=False)
 run(['systemd-run','--collect','--on-active=15min','--unit=tx-mihomo-activation-rollback','/usr/local/libexec/mihomo-tx-control','rollback'],check=True)

def activate():
 global DEADLINE
 kernelcheck()
 d=json.loads(DEP.read_text())
 config=DEP.parent/'active/config.yaml'
 if hashlib.sha256(config.read_bytes()).hexdigest()!=d['version']:raise RuntimeError('deployment config hash mismatch')
 run(['/usr/local/bin/mihomo','-t','-d',str(config.parent)],timeout=30,check=True)
 if state().get('phase') in ('failed','recovering'):raise RuntimeError('complete recovery and inspect status before activation')
 armrestore()
 try:
  run(['systemctl','stop',UNIT],timeout=135,check=True)
  cleanup()
  DEADLINE=None
  prepare()
  with locked():
   d=json.loads(DEP.read_text());d['enabled']=True
   # A past OnBootSec may fire immediately: this activation uses its own
   # accept deadline; the next real boot must still pass boot confirmation.
   d['origin_boot_id']=bootid();deploysave(d)
  run(['systemctl','stop','mihomo.service'],timeout=30,check=True)
  run(['systemctl','reset-failed',UNIT])
  run(['systemctl','start',UNIT],timeout=65,check=True)
  health()
  if state().get('phase')!='active':raise RuntimeError('activation health failed')
  run(['systemctl','disable','mihomo.service'],check=True)
  run(['systemctl','enable',UNIT,'mihomo-tx-health.timer','mihomo-tx-boot-confirm.timer'],check=True)
  run(['systemctl','start','mihomo-tx-health.timer','mihomo-tx-boot-confirm.timer'],check=True)
 except Exception:
  rollback();raise
 print('ACTIVE_PENDING_ACCEPT: verify new SSH and run accept within 15 minutes')

def accept():
 health()
 with locked():
  if state().get('phase')!='active' or not json.loads(DEP.read_text()).get('enabled'):raise RuntimeError('active deployment is not healthy')
  run(['systemctl','stop','tx-mihomo-activation-rollback.timer'],check=True)
  if run(['systemctl','is-active','tx-mihomo-activation-rollback.service']).stdout.strip() in ('active','activating'):raise RuntimeError('rollback has already started')
 print('ACTIVATION_ACCEPTED')

def restart():
 if not json.loads(DEP.read_text()).get('enabled'):raise RuntimeError('deployment disabled after rollback; use activate, then accept')
 activate()

def health():
 s=state()
 if s['phase']!='active':
  if s['phase'] in ('failed','recovering'):print('TX_RECOVERY_WARNING',s['phase'],s.get('cleanup_errors',[]),file=sys.stderr)
  return
 try:
  p=run(['dig','@127.0.0.1','-p',s.get('dns_port','53'),'ipinfo.io','+time=1','+tries=1','+short'],timeout=3)
  responsive=p.returncode==0 and bool(p.stdout.strip())
 except subprocess.TimeoutExpired:responsive=False
 actual=run(['resolvectl','dns','eth0'],check=True).stdout
 dnsservers=actual.partition(': ')[2].split()
 expected='127.0.0.1' if s.get('dns_port','53')=='53' else '127.0.0.1:'+s['dns_port']
 drift=dnsservers!=[expected]
 for family in ['-4','-6']:
  rules=json.loads(run(['ip',family,'-j','rule'],check=True).stdout)
  priorities={r.get('priority') for r in rules}
  if not ({18000+i for i in range(len(s.get('guard_tcp_ports',[22,80,443])))}|{19000,19001,19002,19010}).issubset(priorities):drift=True
  for i,port in enumerate(s.get('guard_tcp_ports',[22,80,443])):
   matching=[r for r in rules if r.get('priority')==18000+i]
   if len(matching)!=1 or str(matching[0].get('sport'))!=str(port) or matching[0].get('table')!='main' or matching[0].get('ipproto')!='tcp':drift=True
  if not run(['ip',family,'route','show','table','20220'],check=True).stdout.strip():drift=True
 if run(['nft','list','table','inet','mihomo']).returncode:drift=True
 ok=responsive and not drift
 with locked():
  s=state()
  if s['phase']!='active':return
  s['failures']=0 if ok else s.get('failures',0)+1;save(s)
  recover=s['failures']>=2 or drift
 if recover:rollback(force=not responsive)

if __name__=='__main__':
 try:
  a=sys.argv[1]
  if a=='guard-up':guardup()
  elif a=='dns-up':dnsup(sys.argv[2] if len(sys.argv)>2 else '53')
  elif a=='cleanup':cleanup()
  elif a=='stopped':stopped()
  elif a=='rollback':rollback()
  elif a=='health':health()
  elif a=='boot-check':bootcheck()
  elif a=='confirm':confirm()
  elif a=='restart':restart()
  elif a=='activate':activate()
  elif a=='accept':accept()
  elif a=='status':status()
  elif a=='prepare':prepare(len(sys.argv)>2 and sys.argv[2]=='nodns')
  elif a=='tun-clean':
   errors=tunremove();print(errors);sys.exit(bool(errors))
  else:raise RuntimeError('unknown action')
 except Exception as e:print('TX_CONTROL_ERROR',str(e),file=sys.stderr);sys.exit(1)
