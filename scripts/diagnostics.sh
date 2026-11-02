#!/usr/bin/env bash
# `cond && result ... || result ...` безопасен: result() всегда возвращает 0.
# shellcheck disable=SC2015
# Own node diagnostics: facts, DNS/DPI probes, perf baseline.
# Non-interactive by design (for Ansible `script` runs). Every probe has a
# timeout and never aborts the whole run; missing tools are SKIPped.
# Machine-readable lines: `RESULT <name> <OK|FAIL|WARN|SKIP> <detail>`.
set -u
export LC_ALL=C

DIAG_IPERF_SERVER="${DIAG_IPERF_SERVER:-}"
DIAG_PANEL_URL="${DIAG_PANEL_URL:-}"
DIAG_FULL="${DIAG_FULL:-0}"
DIAG_SNI_LIST="${DIAG_SNI_LIST:-example.com youtube.com instagram.com discord.com}"
# shellcheck disable=SC2206
DIAG_SNI_ARR=($DIAG_SNI_LIST)
DIAG_DNS_LIST="${DIAG_DNS_LIST:-1.1.1.1 8.8.8.8 77.88.8.8 9.9.9.9}"
# shellcheck disable=SC2206
DIAG_DNS_ARR=($DIAG_DNS_LIST)
DIAG_TG_DCS="${DIAG_TG_DCS:-149.154.175.50 149.154.167.51 149.154.175.100 149.154.167.91 149.154.171.5 91.108.56.130}"
# shellcheck disable=SC2206
DIAG_TG_ARR=($DIAG_TG_DCS)

N_OK=0; N_FAIL=0; N_WARN=0; N_SKIP=0
result() { # name status detail
    printf 'RESULT %s %s %s\n' "$1" "$2" "$3"
    case "$2" in
        OK) N_OK=$((N_OK+1)) ;;
        FAIL) N_FAIL=$((N_FAIL+1)) ;;
        WARN) N_WARN=$((N_WARN+1)) ;;
        *) N_SKIP=$((N_SKIP+1)) ;;
    esac
}
section() { printf '\n### %s\n' "$1"; }
have() { command -v "$1" >/dev/null 2>&1; }

need_value() {
    # Без значения `shift 2` не сдвигает аргументы, и цикл ниже не завершается.
    if [[ $# -lt 2 || -z "$2" ]]; then
        echo "Missing value for $1" >&2
        exit 2
    fi
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --iperf-server) need_value "$@"; DIAG_IPERF_SERVER="$2"; shift 2 ;;
        --panel-url) need_value "$@"; DIAG_PANEL_URL="$2"; shift 2 ;;
        --full) DIAG_FULL=1; shift ;;
        --sni-list) need_value "$@"; DIAG_SNI_LIST="$2"
            read -r -a DIAG_SNI_ARR <<<"$DIAG_SNI_LIST"; shift 2 ;;
        *) echo "Unknown arg: $1" >&2; exit 2 ;;
    esac
done

echo "diagnostics (full=${DIAG_FULL}) at $(date -u +%FT%TZ)"

# ---------- facts ----------
section "facts"
CPU_MODEL="$(grep -m1 'model name' /proc/cpuinfo 2>/dev/null | cut -d: -f2 | xargs)"
CPU_MODEL="${CPU_MODEL:-unknown}"
CPU_N="$(nproc 2>/dev/null || echo unknown)"
MEM_MB="$(awk '/MemTotal/ {printf "%d", $2/1024}' /proc/meminfo 2>/dev/null || echo unknown)"
DISK_ROOT="$(df -h / 2>/dev/null | awk 'NR==2 {print $2 " total, " $4 " avail (" $5 " used)"}' || echo unknown)"
OS_PRETTY="$(grep -m1 PRETTY_NAME /etc/os-release 2>/dev/null | cut -d= -f2 | tr -d '"' || echo unknown)"
KERNEL="$(uname -r 2>/dev/null || echo unknown)"
if have systemd-detect-virt; then
    VIRT="$(systemd-detect-virt 2>/dev/null || echo unknown)"
elif grep -q hypervisor /proc/cpuinfo 2>/dev/null; then
    VIRT="vm?"
else
    VIRT="unknown"
fi
UPTIME_S="$(awk '{print int($1)}' /proc/uptime 2>/dev/null || echo 0)"
LOAD="$(awk '{print $1","$2","$3}' /proc/loadavg 2>/dev/null || echo unknown)"
CC="$(sysctl -n net.ipv4.tcp_congestion_control 2>/dev/null || echo unknown)"
QDISC="$(sysctl -n net.core.default_qdisc 2>/dev/null || echo unknown)"
echo "cpu=${CPU_MODEL} x${CPU_N} mem=${MEM_MB}MB disk[/]=${DISK_ROOT}"
echo "os=${OS_PRETTY} kernel=${KERNEL} virt=${VIRT} uptime=${UPTIME_S}s load=${LOAD}"
echo "cc=${CC} qdisc=${QDISC}"
result facts OK "${CPU_MODEL} x${CPU_N} / ${MEM_MB}MB"

IPV4="$(timeout 8 curl -4 -s --max-time 6 https://api.ipify.org 2>/dev/null || true)"
IPV6="$(timeout 8 curl -6 -s --max-time 6 https://api6.ipify.org 2>/dev/null || true)"
[ -z "$IPV4" ] && result ipv4 FAIL "no IPv4 egress" || result ipv4 OK "$IPV4"
[ -z "$IPV6" ] && result ipv6 SKIP "no IPv6" || result ipv6 OK "$IPV6"
if [ -n "$IPV4" ] && have dig; then
    REV="$(awk -F. '{print $4"."$3"."$2"."$1}' <<<"$IPV4")"
    ASN_TXT="$(timeout 8 dig +short +time=3 +tries=1 "${REV}.origin.asn.cymru.com" TXT 2>/dev/null | tr -d '"' || true)"
    [ -z "$ASN_TXT" ] && result asn WARN "cymru no answer" || result asn OK "$ASN_TXT"
else
    result asn SKIP "need IPv4+dig"
fi

# ---------- DNS ----------
section "dns"
SYS_DNS="$(grep -m1 nameserver /etc/resolv.conf 2>/dev/null | awk '{print $2}' || echo unknown)"
echo "system resolver: ${SYS_DNS}"
for dom in example.com youtube.com; do
    if have getent && getent hosts "$dom" >/dev/null 2>&1; then
        result "dns-sys/$dom" OK "$(getent hosts "$dom" | awk '{print $1}' | head -1)"
    else
        result "dns-sys/$dom" FAIL "system resolver"
    fi
done
if have dig; then
    for srv in "${DIAG_DNS_ARR[@]}"; do
        for dom in example.com youtube.com; do
            A="$(timeout 6 dig +short +time=3 +tries=1 "@${srv}" "$dom" A 2>/dev/null | grep -E '^[0-9.]+$' | head -1 || true)"
            [ -z "$A" ] && result "dns@${srv}/$dom" FAIL "no A" || result "dns@${srv}/$dom" OK "$A"
        done
    done
else
    result dns-external SKIP "no dig"
fi

# ---------- DoH ----------
section "doh"
if have curl; then
    for doh in "https://cloudflare-dns.com/dns-query?name=example.com&type=A" "https://dns.google/resolve?name=example.com&type=A"; do
        CODE="$(timeout 10 curl -s -o /dev/null -w "%{http_code}" --max-time 8 -H 'accept: application/dns-json' "$doh" 2>/dev/null || echo 000)"
        [ "$CODE" = "200" ] && result "doh/${doh#https://}" OK "http 200" || result "doh/${doh#https://}" FAIL "http $CODE"
    done
else
    result doh SKIP "no curl"
fi

# ---------- telegram ----------
section "telegram"
for dc in "${DIAG_TG_ARR[@]}"; do
    if timeout 5 bash -c "cat < /dev/null > /dev/tcp/${dc}/443" 2>/dev/null; then
        result "tg-dc/$dc" OK "443 open"
    else
        result "tg-dc/$dc" FAIL "443 closed/timeout"
    fi
done

# ---------- SNI probes (differential: same IP, different SNI) ----------
section "sni"
if have openssl; then
    for sni in "${DIAG_SNI_ARR[@]}"; do
        OUT="$(timeout 10 openssl s_client -connect 1.1.1.1:443 -servername "$sni" </dev/null 2>&1 || true)"
        # "Verify return code" печатается и при оборванном рукопожатии; успех —
        # только если от сервера пришли данные и согласован шифр.
        if grep -Eq "SSL handshake has read [1-9][0-9]* bytes" <<<"$OUT" && ! grep -q "Cipher is (NONE)" <<<"$OUT"; then
            result "sni/$sni" OK "tls handshake completed"
        elif grep -qi "reset\|connection refused" <<<"$OUT"; then
            result "sni/$sni" FAIL "connection reset (possible DPI)"
        elif [ -z "$OUT" ]; then
            result "sni/$sni" FAIL "timeout (possible DPI drop)"
        else
            result "sni/$sni" WARN "unexpected: $(head -c 80 <<<"$OUT" | tr '\n' ' ')"
        fi
    done
else
    result sni SKIP "no openssl"
fi

# ---------- http ----------
section "http"
if have curl; then
    for u in "https://www.google.com/generate_204" "https://www.youtube.com/generate_204"; do
        R="$(timeout 12 curl -s -o /dev/null -w "%{http_code} %{time_total}s" --max-time 10 "$u" 2>/dev/null || echo "000 timeout")"
        case "$R" in
            204*) result "http/${u#https://}" OK "$R" ;;
            000*) result "http/${u#https://}" FAIL "$R" ;;
            *) result "http/${u#https://}" WARN "$R" ;;
        esac
    done
    if [ -n "$DIAG_PANEL_URL" ]; then
        R="$(timeout 12 curl -sk -o /dev/null -w "%{http_code} %{time_total}s" --max-time 10 "$DIAG_PANEL_URL" 2>/dev/null || echo "000 timeout")"
        case "$R" in
            2*|3*) result "http/panel" OK "$R" ;;
            000*) result "http/panel" FAIL "$R" ;;
            *) result "http/panel" WARN "$R" ;;
        esac
    else
        result "http/panel" SKIP "no --panel-url"
    fi
else
    result http SKIP "no curl"
fi

# ---------- cpu ----------
section "cpu"
if have sysbench; then
    T="$([ "$DIAG_FULL" = "1" ] && echo 30 || echo 10)"
    EVENTS="$(timeout 60 sysbench cpu --threads=1 --time="$T" run 2>/dev/null | awk '/events per second:/ {print $4}' || true)"
    [ -z "$EVENTS" ] && result sysbench FAIL "no result" || result sysbench OK "${EVENTS} events/s (${T}s,1 thread)"
else
    result sysbench SKIP "no sysbench"
fi

# ---------- disk ----------
section "disk"
if have fio; then
    SZ="$([ "$DIAG_FULL" = "1" ] && echo 1G || echo 256M)"
    RT="$([ "$DIAG_FULL" = "1" ] && echo 30 || echo 15)"
    FIO_OUT="$(timeout 120 fio --name=q --rw=randrw --rwmixread=50 --bs=4k --iodepth=32 --numjobs=1 --size="$SZ" --runtime="$RT" --time_based --direct=1 --filename=/var/tmp/diag-fio-test --output-format=json 2>/dev/null || true)"
    rm -f /var/tmp/diag-fio-test
    if [ -z "$FIO_OUT" ]; then
        result fio FAIL "no result"
    elif have python3; then
        FIO_SUM="$(python3 -c 'import json,sys; d=json.load(sys.stdin); j=d["jobs"][0]; r=j["read"]; w=j["write"]; print("read %.1fMiB/s %diops write %.1fMiB/s %diops" % (r["bw"]/1024, r["iops"], w["bw"]/1024, w["iops"]))' <<<"$FIO_OUT" 2>/dev/null || true)"
        [ -z "$FIO_SUM" ] && result fio WARN "unparsed output" || result fio OK "$FIO_SUM (${SZ}/${RT}s)"
    else
        result fio WARN "no python3 to parse"
    fi
else
    result fio SKIP "no fio"
fi

# ---------- iperf ----------
section "iperf"
if [ -n "$DIAG_IPERF_SERVER" ]; then
    if have iperf3; then
        T="$([ "$DIAG_FULL" = "1" ] && echo 30 || echo 10)"
        IPERF_OUT="$(timeout 90 iperf3 -c "$DIAG_IPERF_SERVER" -t "$T" -J 2>/dev/null || true)"
        if [ -z "$IPERF_OUT" ]; then
            result iperf FAIL "no result from $DIAG_IPERF_SERVER"
        elif have python3; then
            IPERF_SUM="$(python3 -c 'import json,sys; d=json.load(sys.stdin); s=d["end"]["sum_sent"]["bits_per_second"]/1e6; r=d["end"]["sum_received"]["bits_per_second"]/1e6; print("sent %.1fMbit/s recv %.1fMbit/s" % (s, r))' <<<"$IPERF_OUT" 2>/dev/null || true)"
            [ -z "$IPERF_SUM" ] && result iperf WARN "unparsed output" || result iperf OK "$IPERF_SUM (${T}s)"
        else
            result iperf WARN "no python3 to parse"
        fi
    else
        result iperf SKIP "no iperf3"
    fi
    PING="$(timeout 30 ping -c 10 -q "$DIAG_IPERF_SERVER" 2>/dev/null | awk -F'[ ,%]+' '/packet loss/ {print "loss="$6"%"} /rtt/ {print " rtt="$4}' | tr -d '\n' || true)"
    [ -z "$PING" ] && result ping FAIL "$DIAG_IPERF_SERVER" || result ping OK "$PING"
else
    result iperf SKIP "no --iperf-server"
    result ping SKIP "no --iperf-server"
fi

echo
echo "SUMMARY ok=${N_OK} fail=${N_FAIL} warn=${N_WARN} skip=${N_SKIP}"
