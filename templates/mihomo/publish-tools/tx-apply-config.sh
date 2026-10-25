#!/usr/bin/env bash
# TX skill 发布工具：--check 只校验；--publish 应用当前源文件。
# 新订阅的源文件与稳定回滚配置须先按 skill 准备；发布后仍需新 SSH 验收及 accept。
set -euo pipefail
TX_CHECK_ONLY=0
case "${1:-}" in
  --check) TX_CHECK_ONLY=1 ;;
  --publish) ;;
  --accept) ;;
  *) printf '%s\n' '用法：sudo bash tx-apply-config.sh --check | --publish | --accept' >&2; exit 2 ;;
esac
[[ $# -eq 1 && ${EUID} -eq 0 ]] || { printf '%s\n' '需要 root，且仅允许 --check、--publish 或 --accept。' >&2; exit 2; }
TX_ROOT=/home/serveruser/.config/mihomo/tx
TX_ACTIVE=/var/lib/mihomo-tx/active
TX_CONTROL=/usr/local/libexec/mihomo-tx-control
TX_ROLLBACK_UNIT=tx-config-update-rollback
TX_WINDOW_DROPIN=/run/systemd/system/tx-mihomo-activation-rollback.timer.d/90-tx-config-publish.conf
if [[ "$1" == --accept ]]; then
  for TX_CHECK_UNIT in "$TX_ROLLBACK_UNIT.service" tx-mihomo-activation-rollback.service; do
    TX_UNIT_STATE=$(systemctl show "$TX_CHECK_UNIT" -p ActiveState --value 2>/dev/null || true)
    case "$TX_UNIT_STATE" in active|activating|deactivating) printf '%s\n' '回滚已开始，拒绝保留本轮发布。' >&2; exit 1;; esac
  done
  "$TX_CONTROL" accept
  systemctl stop "$TX_ROLLBACK_UNIT.timer"
  for TX_CHECK_UNIT in "$TX_ROLLBACK_UNIT.service" tx-mihomo-activation-rollback.service; do
    TX_UNIT_STATE=$(systemctl show "$TX_CHECK_UNIT" -p ActiveState --value 2>/dev/null || true)
    case "$TX_UNIT_STATE" in active|activating|deactivating) printf '%s\n' '回滚已开始，保留失败，请检查 status。' >&2; exit 1;; esac
  done
  rm -f -- "$TX_WINDOW_DROPIN"
  systemctl daemon-reload
  "$TX_CONTROL" status
  exit 0
fi
node --check "$TX_ROOT/webshare-dns.js"
python3 "$(dirname "${BASH_SOURCE[0]}")/check-base.py" "$TX_ROOT/base.yaml" --js "$TX_ROOT/webshare-dns.js"
if (( TX_CHECK_ONLY )); then
  TX_PREVIEW=$(mktemp "$TX_ROOT/config.preflight-XXXXXXXX.yaml")
  trap 'rm -f -- "$TX_PREVIEW"' EXIT
  chown serveruser:serveruser "$TX_PREVIEW"
  chmod 600 "$TX_PREVIEW"
  runuser -u serveruser -- python3 "$TX_ROOT/build-config.py" tun "$TX_PREVIEW"
  runuser -u serveruser -- /usr/local/bin/mihomo -t -d "$TX_ACTIVE" -f "$TX_PREVIEW"
  printf '%s\n' 'PREFLIGHT_OK：仅生成临时候选并检查，未发布、未启停服务。'
  exit 0
fi
"$TX_CONTROL" health
python3 - <<'STATE'
import json
from pathlib import Path
s=json.loads(Path('/run/mihomo-tx/state.json').read_text())
d=json.loads(Path('/var/lib/mihomo-tx/deployment.json').read_text())
if s.get('phase')!='active' or s.get('cleanup_errors') or not d.get('enabled'):
    raise SystemExit('当前不是健康的正式运行状态，先检查 status 并处理恢复，禁止直接发布')
STATE
TX_STOPPED=0
TX_ROLLBACK_ARMED=0
TX_BACKUP=''
# 拒绝同一发布脚本重入；不要用网络控制锁包住服务启停。
exec 8>/run/tx-config-publish.lock
chmod 600 /run/tx-config-publish.lock
flock -n 8 || { printf '%s\n' '另一个配置发布正在执行。' >&2; exit 1; }
for TX_CHECK_UNIT in "$TX_ROLLBACK_UNIT.timer" "$TX_ROLLBACK_UNIT.service"; do
  TX_UNIT_STATE=$(systemctl show "$TX_CHECK_UNIT" -p ActiveState --value 2>/dev/null || true)
  case "$TX_UNIT_STATE" in
    active|activating|deactivating)
      printf '%s\n' '已有配置更新的回滚保护/恢复在运行，请先处理它。' >&2
      exit 1;;
  esac
done
TX_CANDIDATE=''
TX_FAIL() {
  local TX_EXIT=$?
  trap - EXIT
  if (( TX_EXIT != 0 )); then
    if (( TX_STOPPED )); then
      printf '%s\n' '发布失败，尝试回滚到原稳定代理；请检查 status。' >&2
      "$TX_CONTROL" rollback || true
    fi
    if (( TX_ROLLBACK_ARMED && ! TX_STOPPED )); then
      systemctl stop "$TX_ROLLBACK_UNIT.timer" || true
    fi
    printf '操作失败；备份目录：%s\n' "${TX_BACKUP:-尚未创建}" >&2
  fi
  if [[ -n "$TX_CANDIDATE" ]]; then rm -f -- "$TX_CANDIDATE"; fi
  exit "$TX_EXIT"
}
trap TX_FAIL EXIT
install -d -m 700 /var/backups/mihomo-tx
TX_BACKUP=$(mktemp -d /var/backups/mihomo-tx/config-update-XXXXXXXX)
cp -p "$TX_ROOT/base.yaml" "$TX_BACKUP/base.yaml"
cp -p "$TX_ROOT/webshare-dns.js" "$TX_BACKUP/webshare-dns.js"
cp -p "$TX_ACTIVE/config.yaml" "$TX_BACKUP/config.yaml"
cp -p /var/lib/mihomo-tx/deployment.json "$TX_BACKUP/deployment.json"
TX_CANDIDATE=$(mktemp "$TX_ROOT/config.publish-XXXXXXXX.yaml")
chown serveruser:serveruser "$TX_CANDIDATE"
chmod 600 "$TX_CANDIDATE"
runuser -u serveruser -- python3 "$TX_ROOT/build-config.py" tun "$TX_CANDIDATE"
runuser -u serveruser -- /usr/local/bin/mihomo -t -d "$TX_ACTIVE" -f "$TX_CANDIDATE"
# 校验完成后才进入有保护的发布阶段。
systemd-run --collect --on-active=20min --unit="$TX_ROLLBACK_UNIT" "$TX_CONTROL" rollback
TX_ROLLBACK_ARMED=1
TX_STOPPED=1
systemctl stop mihomo-tx-candidate.service
# 控制锁内只进行文件事务；服务启停在锁外。
flock -w 10 /run/mihomo-tx/control.lock python3 - "$TX_CANDIDATE" <<'PY'
from pathlib import Path
import json, hashlib, os, subprocess, sys
root = Path('/var/lib/mihomo-tx')
active = root / 'active/config.yaml'
meta = root / 'deployment.json'
state = json.loads(Path('/run/mihomo-tx/state.json').read_text())
pid = subprocess.check_output(
    ['systemctl', 'show', 'mihomo-tx-candidate.service', '-p', 'MainPID', '--value'],
    text=True).strip()
if pid not in ('', '0') or state.get('phase') != 'stable' or state.get('cleanup_errors'):
    raise SystemExit('正式实例未完全停止或清理未完成，禁止安装候选')
content = Path(sys.argv[1]).read_bytes()
owner = active.stat()
tmp = active.with_name('config.yaml.next')
fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, 'wb') as f:
    f.write(content)
os.chown(tmp, owner.st_uid, owner.st_gid)
tmp.chmod(0o600)
os.replace(tmp, active)
d = json.loads(meta.read_text())
d['version'] = hashlib.sha256(content).hexdigest()
d['enabled'] = False
tmp = meta.with_suffix('.next')
tmp.write_text(json.dumps(d))
tmp.chmod(0o600)
os.replace(tmp, meta)
PY
# 只覆盖本轮激活 timer 的等待时长；不改控制脚本或持久服务配置。
install -d -m 755 "$(dirname "$TX_WINDOW_DROPIN")"
printf '[Timer]\nOnActiveSec=\nOnActiveSec=20min\n' > "$TX_WINDOW_DROPIN"
chmod 644 "$TX_WINDOW_DROPIN"
systemctl daemon-reload
"$TX_CONTROL" activate
for TX_CHECK_UNIT in "$TX_ROLLBACK_UNIT.service" tx-mihomo-activation-rollback.service; do
  TX_UNIT_STATE=$(systemctl show "$TX_CHECK_UNIT" -p ActiveState --value 2>/dev/null || true)
  case "$TX_UNIT_STATE" in active|activating|deactivating) printf '%s\n' '回滚已开始，禁止重新计时。' >&2; exit 1;; esac
done
# 激活完成后统一重新计时，给用户回复 15 分钟，并保留 Mac 验收余量。
systemctl restart "$TX_ROLLBACK_UNIT.timer" tx-mihomo-activation-rollback.timer
systemctl list-timers --all "$TX_ROLLBACK_UNIT.timer" tx-mihomo-activation-rollback.timer
"$TX_CONTROL" status
printf '\n已启用候选，自动回滚窗口约二十分钟；前十五分钟等待用户第二出口验收。备份：%s\n' "$TX_BACKUP"
printf '%s\n' \
  '先提示用户用第二出口新建 SSH；十五分钟无回复才用 Mac 全新 SSH 验收。' \
  '用户测试前的回复优先；失败立即回滚。成功且服务健康时执行：' \
  'sudo bash /home/serveruser/.codex/skills/tx-mihomo-config-publish/scripts/tx-apply-config.sh --accept' \
  'systemctl is-active tx-config-update-rollback.service' \
  'sudo /usr/local/libexec/mihomo-tx-control status' \
  '如果手工回滚服务 active/activating，不应把本次发布认定为已保留。' \
  '新版本首次真实重启仍须十分钟内执行 control confirm。'
