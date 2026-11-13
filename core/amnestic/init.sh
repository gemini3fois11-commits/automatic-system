#!/bin/bash
# Amnestic Volatility — RAM-only mount initializer
# Mounts all writable paths into tmpfs so zero bytes touch persistent storage.
set -euo pipefail

OMEGA_LOG="/run/omega-tails/amnestic.log"
mkdir -p /run/omega-tails
exec > >(tee -a "$OMEGA_LOG") 2>&1

log() { echo "[AMNESTIC $(date -u +%T)] $*"; }

VOLATILE_MOUNTS=(
    /tmp
    /var/log
    /var/tmp
    /var/spool
    /var/cache
    /home
    /root
    /run/user
)

RAM_SIZE_MB=$(awk '/MemTotal/{printf "%d", $2/1024}' /proc/meminfo)
# Reserve 40% of RAM for the system; give volatile mounts up to 30%
TMPFS_LIMIT="$((RAM_SIZE_MB * 30 / 100))m"

log "Total RAM: ${RAM_SIZE_MB}MB — tmpfs ceiling: ${TMPFS_LIMIT}"

for mnt in "${VOLATILE_MOUNTS[@]}"; do
    if mountpoint -q "$mnt" 2>/dev/null; then
        log "SKIP $mnt (already mounted)"
        continue
    fi
    mkdir -p "$mnt"
    mount -t tmpfs -o "mode=1777,size=${TMPFS_LIMIT},noexec,nosuid,nodev" \
        tmpfs-omega "$mnt" \
        && log "MOUNTED tmpfs -> $mnt" \
        || log "WARN: could not mount $mnt"
done

# Lock /proc/sys/kernel/dmesg_restrict so logs don't leak
echo 1 > /proc/sys/kernel/dmesg_restrict 2>/dev/null || true

log "Amnestic Volatility layer: ACTIVE"
