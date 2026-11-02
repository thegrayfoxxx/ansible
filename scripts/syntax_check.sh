#!/usr/bin/env bash
# ansible-playbook --syntax-check для всех плейбуков (локально и в CI).
# target обязателен для host-шаблонов, *_move — ещё и *_move_dest.
set -euo pipefail
cd "$(dirname "$0")/.."

inv="$(mktemp)"
trap 'rm -f "$inv"' EXIT
printf 'localhost ansible_connection=local\n' >"$inv"

rc=0
for pb in playbooks/*.yml; do
    extra='{"target":"all","remnanode_move_dest":"localhost","crowdsec_move_dest":"localhost","nginx_move_dest":"localhost"}'
    if ! out="$(ansible-playbook -i "$inv" --syntax-check "$pb" -e "$extra" 2>&1)"; then
        echo "FAIL $pb"
        echo "$out"
        rc=1
    else
        echo "ok   $pb"
    fi
done
exit "$rc"
