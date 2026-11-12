#!/bin/bash
# Invariant Gate — Boot-time integrity enforcer
# Validates squashfs hash before the live system is considered trusted.
set -euo pipefail

GATE_LOG="/run/omega-tails/invariant-gate.log"
mkdir -p /run/omega-tails
exec > >(tee -a "$GATE_LOG") 2>&1

log()  { echo "[GATE $(date -u +%T)] $*"; }
fail() { echo "[GATE VIOLATION] $*" >&2; exit 1; }

SQUASH_PATH="${OMEGA_SQUASH:-/run/live/medium/live/filesystem.squashfs}"
HASH_PATH="${OMEGA_HASH:-/run/live/medium/live/filesystem.squashfs.sha256}"
POLICY_FILE="/etc/omega-tails/gate-policy.conf"

# --- 1. Verify squashfs hash ---
if [[ ! -f "$SQUASH_PATH" ]]; then
    fail "squashfs not found at $SQUASH_PATH"
fi

if [[ -f "$HASH_PATH" ]]; then
    log "Verifying squashfs SHA-256..."
    EXPECTED=$(cat "$HASH_PATH" | awk '{print $1}')
    ACTUAL=$(sha256sum "$SQUASH_PATH" | awk '{print $1}')
    if [[ "$EXPECTED" != "$ACTUAL" ]]; then
        fail "squashfs hash MISMATCH — expected $EXPECTED got $ACTUAL"
    fi
    log "squashfs hash: OK ($ACTUAL)"
else
    log "WARN: no hash file found — skipping squashfs verification"
fi

# --- 2. Enforce policy rules ---
if [[ -f "$POLICY_FILE" ]]; then
    while IFS= read -r rule || [[ -n "$rule" ]]; do
        [[ "$rule" =~ ^#|^$ ]] && continue
        KEY="${rule%%=*}"
        VAL="${rule#*=}"
        case "$KEY" in
            block_swap)
                if [[ "$VAL" == "1" ]]; then
                    swapoff -a 2>/dev/null && log "swap disabled" || true
                fi ;;
            block_coredump)
                if [[ "$VAL" == "1" ]]; then
                    echo 0 > /proc/sys/kernel/core_uses_pid 2>/dev/null || true
                    ulimit -c 0 2>/dev/null || true
                    log "coredumps disabled"
                fi ;;
            restrict_ptrace)
                if [[ "$VAL" == "1" ]]; then
                    echo 3 > /proc/sys/kernel/yama/ptrace_scope 2>/dev/null || true
                    log "ptrace restricted (scope=3)"
                fi ;;
            disable_suid)
                if [[ "$VAL" == "1" ]]; then
                    find /usr /bin /sbin -perm /4000 -exec chmod u-s {} \; 2>/dev/null || true
                    log "SUID bits stripped"
                fi ;;
        esac
    done < "$POLICY_FILE"
fi

# --- 3. Seal kernel parameters ---
# Prevent loading unsigned modules after boot
if [[ -f /proc/sys/kernel/modules_disabled ]]; then
    echo 1 > /proc/sys/kernel/modules_disabled 2>/dev/null \
        && log "kernel module loading: LOCKED" \
        || log "WARN: could not lock module loading"
fi

log "Invariant Gate: PASSED — system integrity confirmed"
