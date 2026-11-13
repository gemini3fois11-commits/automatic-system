#!/bin/bash
# Void Monitor — Persistent-storage write sentinel
# Watches block devices and mount table for unauthorized persistence attempts.
set -euo pipefail

MONITOR_LOG="/run/omega-tails/void-monitor.log"
ALERT_CONF="/etc/omega-tails/void-monitor-alerts.conf"
PID_FILE="/run/omega-tails/void-monitor.pid"

mkdir -p /run/omega-tails
echo $$ > "$PID_FILE"
exec > >(tee -a "$MONITOR_LOG") 2>&1

log()   { echo "[VOID $(date -u +%T)] $*"; }
alert() {
    echo "[VOID ALERT $(date -u +%T)] $*" | tee -a "$MONITOR_LOG"
    # Notify all logged-in users
    wall "⚠ OMEGA-TAILS VOID ALERT: $*" 2>/dev/null || true
    # Optional: halt if policy is LOCKDOWN
    if grep -q "^on_violation=halt" "$ALERT_CONF" 2>/dev/null; then
        log "LOCKDOWN triggered — halting system"
        systemctl halt --force 2>/dev/null || halt -f
    fi
}

log "Void Monitor starting — PID $$"

# --- Baseline snapshot of mounted filesystems ---
declare -A BASELINE_MOUNTS
while IFS= read -r line; do
    dev=$(echo "$line" | awk '{print $1}')
    mnt=$(echo "$line" | awk '{print $2}')
    type=$(echo "$line" | awk '{print $3}')
    BASELINE_MOUNTS["$mnt"]="$dev:$type"
done < <(cat /proc/mounts)
log "Baseline: ${#BASELINE_MOUNTS[@]} mount points recorded"

# --- Identify physical block devices to watch ---
BLOCK_DEVICES=()
while IFS= read -r dev; do
    # Skip loop, ram, tmpfs-backed devices
    [[ "$dev" =~ ^loop|^ram ]] && continue
    BLOCK_DEVICES+=("$dev")
done < <(lsblk -ndo NAME 2>/dev/null || true)

log "Watching block devices: ${BLOCK_DEVICES[*]:-none}"

# --- Main watch loop ---
while true; do
    sleep 5

    # Check for new mounts that weren't in baseline
    while IFS= read -r line; do
        dev=$(echo "$line" | awk '{print $1}')
        mnt=$(echo "$line" | awk '{print $2}')
        type=$(echo "$line" | awk '{print $3}')
        opts=$(echo "$line" | awk '{print $4}')

        [[ -v "BASELINE_MOUNTS[$mnt]" ]] && continue
        [[ "$type" == "tmpfs" || "$type" == "devtmpfs" || "$type" == "sysfs" \
           || "$type" == "proc" || "$type" == "cgroup"* || "$type" == "pstore" \
           || "$type" == "securityfs" || "$type" == "efivarfs" ]] && continue

        # New non-volatile mount detected
        if [[ "$opts" != *"ro"* ]]; then
            alert "NEW WRITABLE MOUNT: $dev on $mnt (type=$type opts=$opts)"
        else
            log "new read-only mount: $dev on $mnt (type=$type) — OK"
            BASELINE_MOUNTS["$mnt"]="$dev:$type"
        fi
    done < <(cat /proc/mounts)

    # Check swap is still off
    if [[ -s /proc/swaps ]] && awk 'NR>1' /proc/swaps | grep -q .; then
        alert "SWAP DETECTED — memory may be written to disk"
        swapoff -a 2>/dev/null || true
    fi

done
