#!/bin/bash
# OMEGA-TAILS QEMU test runner
# Tests the ISO in a VM without touching any host disk.
set -euo pipefail

ISO="${1:-}"
[[ -z "$ISO" ]] && { echo "Usage: $0 path/to/omega-tails.iso"; exit 1; }
[[ -f "$ISO" ]] || { echo "ISO not found: $ISO"; exit 1; }

command -v qemu-system-x86_64 >/dev/null 2>&1 || { echo "qemu not installed"; exit 1; }

RAM_MB=2048
CPUS=2

echo "[TEST] Booting $ISO in QEMU (RAM=${RAM_MB}MB, CPUs=${CPUS})"
echo "[TEST] No disk image — purely RAM-based boot"

qemu-system-x86_64 \
    -m "${RAM_MB}M" \
    -smp "${CPUS}" \
    -cdrom "$ISO" \
    -boot d \
    -net nic,model=virtio \
    -net user \
    -vga virtio \
    -enable-kvm \
    -no-reboot \
    -serial stdio \
    -display sdl 2>/dev/null \
    || qemu-system-x86_64 \
        -m "${RAM_MB}M" \
        -smp "${CPUS}" \
        -cdrom "$ISO" \
        -boot d \
        -net nic,model=virtio \
        -net user \
        -vga virtio \
        -no-reboot \
        -nographic
