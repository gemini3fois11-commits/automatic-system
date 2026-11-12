#!/bin/bash
# OMEGA-TAILS ISO Build Script
# Requires: live-build, debootstrap, squashfs-tools, xorriso
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="$SCRIPT_DIR/output"
OVERLAY_DIR="$REPO_ROOT/overlay"

log() { echo "[BUILD $(date -u +%T)] $*"; }
die() { echo "[BUILD ERROR] $*" >&2; exit 1; }

command -v lb >/dev/null 2>&1 || die "live-build not installed (apt install live-build)"
command -v xorriso >/dev/null 2>&1 || die "xorriso not installed"

mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"

log "Configuring live-build..."
lb config \
    --distribution bookworm \
    --architectures amd64 \
    --archive-areas "main contrib non-free non-free-firmware" \
    --bootloader syslinux \
    --binary-image iso-hybrid \
    --memtest memtest86+ \
    --iso-application "OMEGA-TAILS" \
    --iso-publisher "omega-tails" \
    --iso-volume "OMEGATAILS" \
    --compression xz \
    --debian-installer false \
    --win32-loader false

log "Installing package list..."
cp "$SCRIPT_DIR/config/packages.list" config/package-lists/omega.list.chroot

log "Copying overlay files..."
cp -r "$OVERLAY_DIR/." config/includes.chroot/

log "Copying hooks..."
cp "$SCRIPT_DIR/config/hooks/"*.hook.chroot config/hooks/normal/ 2>/dev/null || true

log "Starting build (this takes 10-30 minutes)..."
lb build 2>&1 | tee build.log

ISO=$(ls "$BUILD_DIR"/*.hybrid.iso 2>/dev/null | head -1)
if [[ -n "$ISO" ]]; then
    SHA=$(sha256sum "$ISO" | awk '{print $1}')
    echo "$SHA  $(basename "$ISO")" > "${ISO}.sha256"
    log "ISO ready: $ISO"
    log "SHA-256:   $SHA"
else
    die "Build completed but no ISO found — check build.log"
fi
