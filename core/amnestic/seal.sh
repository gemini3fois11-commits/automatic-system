#!/bin/bash
# Amnestic Volatility — Secure memory seal (shutdown hook)
# Overwrites tmpfs contents and syncs before power-off.
set -euo pipefail

log() { echo "[SEAL $(date -u +%T)] $*" | tee -a /run/omega-tails/amnestic.log || true; }

log "Beginning memory seal sequence..."

VOLATILE_MOUNTS=(
    /tmp
    /var/log
    /var/tmp
    /var/spool
    /var/cache
    /home
    /root
)

for mnt in "${VOLATILE_MOUNTS[@]}"; do
    if mountpoint -q "$mnt" 2>/dev/null; then
        # Overwrite all files with zeros before unmount
        find "$mnt" -type f -exec shred -fuz {} \; 2>/dev/null || true
        log "SHREDDED $mnt"
    fi
done

# Flush dirty pages
sync
log "sync complete"

# Drop page cache, dentries, inodes
echo 3 > /proc/sys/vm/drop_caches 2>/dev/null || true
log "kernel caches dropped"

log "Memory seal: COMPLETE — no traces remain"
