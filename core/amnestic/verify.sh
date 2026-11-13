#!/bin/bash
# Amnestic Volatility — Runtime integrity verifier
# Confirms no volatile path has been silently re-mounted as persistent.
set -euo pipefail

PASS=0
FAIL=0

check_tmpfs() {
    local path="$1"
    local fstype
    fstype=$(stat -f -c '%T' "$path" 2>/dev/null || echo "unknown")
    if [[ "$fstype" == "tmpfs" ]]; then
        echo "  [OK]  $path -> tmpfs"
        ((PASS++))
    else
        echo "  [!!]  $path -> $fstype  (PERSISTENCE RISK)"
        ((FAIL++))
    fi
}

echo "=== Amnestic Volatility Verification ==="
for p in /tmp /var/log /var/tmp /home /root; do
    check_tmpfs "$p"
done

echo ""
echo "Result: ${PASS} clean, ${FAIL} at risk"
[[ $FAIL -eq 0 ]] && exit 0 || exit 1
