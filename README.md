# OMEGA-TAILS Live ISO

Amnesiac, RAM-only live system with three core security pillars.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    OMEGA-TAILS BOOT SEQUENCE            │
│                                                         │
│  [1] Invariant Gate ──► squashfs hash verify            │
│         │               kernel hardening                │
│         ▼               policy enforcement              │
│  [2] Amnestic Layer ──► mount all writable paths        │
│         │               to tmpfs (RAM only)             │
│         ▼               zero disk I/O                   │
│  [3] Void Monitor  ──► watch for new persistent         │
│         │               mounts or swap activation       │
│         ▼               alert / halt on violation       │
│  [4] User Session  ──► normal desktop / tools           │
│                                                         │
│  [SHUTDOWN] Amnestic Seal ──► shred all tmpfs files     │
│                               drop kernel caches        │
└─────────────────────────────────────────────────────────┘
```

## Three Pillars

### Amnestic Volatility (`core/amnestic/`)
- All writable paths (`/tmp`, `/home`, `/root`, `/var/log`, ...) mounted as `tmpfs`
- Nothing written to any persistent block device
- On shutdown: `shred` all tmpfs files, `sync`, drop page cache

### Invariant Gate (`core/invariant-gate/`)
- Verifies `filesystem.squashfs` SHA-256 hash at boot
- Enforces security policy: swap off, coredumps disabled, ptrace restricted
- Locks kernel module loading after boot
- System reboots if gate fails

### Void Monitor (`core/void-monitor/`)
- Baselines all mount points at startup
- Polls every 5 seconds for new writable mounts
- Detects swap activation
- Policy: `log` (default) or `halt` on violation

## Build

```bash
# Requires: live-build, debootstrap, xorriso (Debian/Ubuntu)
sudo apt install live-build xorriso debootstrap
sudo bash build/build.sh
```

## Test (QEMU, no disk)

```bash
bash scripts/test-vm.sh build/output/omega-tails.hybrid.iso
```

## Status

```bash
omega-status   # check all three pillars at runtime
```

## File Map

```
core/
  amnestic/         init.sh  seal.sh  verify.sh
  invariant-gate/   gate.sh  policy.conf
  void-monitor/     monitor.sh  alerts.conf
overlay/
  etc/omega-tails/  gate-policy.conf  void-monitor-alerts.conf
  etc/systemd/system/  omega-*.service
  usr/local/bin/    omega-{status,amnestic-init,amnestic-seal,
                          invariant-gate,void-monitor}
build/
  build.sh
  config/packages.list
  config/hooks/0100-omega-install.hook.chroot
scripts/
  test-vm.sh
```
