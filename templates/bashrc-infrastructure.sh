# ---- mihomo proxy ----
proxy_on() {
    export http_proxy=http://127.0.0.1:7890
    export https_proxy=http://127.0.0.1:7890
    export all_proxy=socks5://127.0.0.1:7890
    export no_proxy=localhost,127.0.0.1,::1,mirrors.tencentyun.com,.tencentyun.com
    echo "✅ 代理已开启 (127.0.0.1:7890)"
}

proxy_off() {
    unset http_proxy https_proxy all_proxy no_proxy
    echo "❌ 代理已关闭"
}

proxy_status() {
    if [ -n "$http_proxy" ]; then
        echo "当前状态：代理开启中 ($http_proxy)"
        curl -s --max-time 15 https://www.google.com -o /dev/null && echo "连通性：正常" || echo "连通性：失败"
    else
        echo "当前状态：代理已关闭"
    fi
}

# 默认开启（带提示）
proxy_on

export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"  # This loads nvm
[ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"  # This loads nvm bash_completion

# ---- 系统资源查看 ----
sys() {
    free -b | awk 'function h(b,  i,u){ split("B Ki Mi Gi Ti",u," "); i=1; while(b>=1024 && i<5){b/=1024; i++} return sprintf("%.1f%s",b,u[i]) }
        NR==2{ printf "内存: %s / %s  (已用 %.1f%%)\n", h($3), h($2), $3/$2*100 }'
    df -h / | awk 'NR==2{printf "磁盘: %s / %s  (已用 %s)\n", $3, $2, $5}'
}

# ---- 代理节点管理 ----


# optional local tool environment omitted
# optional local tool environment omitted

# ---- CodeBuddy daemon 管理 ----
# 裸 SSH 会话里 systemctl --user 需要一个 user bus 的环境，这里一并带上。
# 用法：cbd / cbd status / cbd restart / cbd stop
cbd() {
    local uid; uid=$(id -u)
    XDG_RUNTIME_DIR=/run/user/$uid \
    DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$uid/bus \
        systemctl --user "${@:-status}" codebuddy-daemon
}

# ---- TX Webshare startup check (checkws) ----
# 通过 Clash 检查 Webshare 两跳出口；可用 CHECKWS_EXPECTED_IP 覆盖预期 IP。
checkws() {
    local ws_ip
    local ws_expected="${CHECKWS_EXPECTED_IP:-192.0.2.10}"
    if ! ws_ip="$(command curl -q -4 -fsS --connect-timeout 3 --max-time 20 \
        --retry 0 --noproxy '' --proxy http://127.0.0.1:7890 \
        https://ifconfig.me/ip 2>/dev/null)"; then
        printf '%s\n' '❌ Webshare 两跳检测失败：请求未成功，请检查 Clash 和代理连接。'
        return 1
    fi
    ws_ip="$(printf '%s' "$ws_ip" | tr -d '[:space:]')"
    if [ "$ws_ip" = "$ws_expected" ]; then
        printf '✅ Webshare 两跳检测通过（出口 IP：%s）\n' "$ws_ip"
        return 0
    fi
    printf '❌ Webshare 两跳检测失败：出口未匹配（当前：%s，预期：%s）\n' \
        "${ws_ip:-空响应}" "$ws_expected"
    return 1
}
case $- in
    *i*) checkws || : ;;
esac
# ---- end TX Webshare startup check ----

# 第一跳订阅下载：只保存待发布文件，不切换运行配置。
updatesanmao() {
    python3 "$HOME/.config/mihomo/tx/updatesanmao.py" "$@"
}

# 当前代理出口与 getcc HTTP 环境风险估算。
checkcc() {
    python3 "$HOME/.local/bin/checkcc-report.py" "$@"
}
