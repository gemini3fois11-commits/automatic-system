#!/usr/bin/env bash
# ==============================================================================
# PROJET EXERGUE GLOBE — BLUEPRINT D'EXÉCUTION NATIONALE / CIVILE (CLÉ EN MAIN)
# MANDAT SOUVERAIN : Sauf les dettes
# ==============================================================================
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

SUDO="" && command -v sudo &> /dev/null && SUDO="sudo"

echo -e "\033[1;33m[*] [EXERGUE GLOBE] Initialisation du déploiement monolithique complet...\033[0m"

# 1. Purge des anciens résidus de processus
$SUDO pkill -9 -f extergobe_space_core || true
$SUDO pkill -9 -f extergobe_terminal.sh || true

# 2. Création de l'arborescence physique et volatile
export TARGET_DIR="/opt/extergobe"
export WORKSPACE="/dev/shm/.extergobe_workspace"

$SUDO mkdir -p "$TARGET_DIR"/{core,logs,vault} "$WORKSPACE"
$SUDO chmod -R 777 "$TARGET_DIR" "$WORKSPACE"

# 3. Copie du code source C++ dans le répertoire cible
echo -e "\033[1;36m[*] Installation du noyau natif (extergobe_space_core.cpp)...\033[0m"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cp "$SCRIPT_DIR/extergobe_space_core.cpp" "$TARGET_DIR/core/extergobe_space_core.cpp"

# 4. Compilation statique du binaire C++ avec optimisations maximales (-O3)
echo -e "\033[1;32m[*] Compilation du binaire natif statique...\033[0m"
if ! command -v g++ &> /dev/null; then
    $SUDO apt-get update && $SUDO apt-get install -y g++ build-essential libc6-dev
fi

g++ -O3 -static -std=c++20 -march=native \
    "$TARGET_DIR/core/extergobe_space_core.cpp" \
    -o "$TARGET_DIR/core/extergobe_space_core" -lrt
$SUDO chmod +x "$TARGET_DIR/core/extergobe_space_core"

# 5. Écriture du terminal de cartographie tactique
echo -e "\033[1;36m[*] Création du terminal de cartographie (extergobe_terminal.sh)...\033[0m"
cat << 'EOF' > "$TARGET_DIR/core/extergobe_terminal.sh"
#!/usr/bin/env bash
set -euo pipefail

WORKSPACE="/dev/shm/.extergobe_workspace"
PORT_FILE="$WORKSPACE/.network_port"
LOG_FILE="/opt/extergobe/logs/extergobe_telemetry.log"

while true; do
    clear
    ACTIVE_PORT="DISCONNECTED"
    if [ -f "$PORT_FILE" ]; then
        ACTIVE_PORT=$(cat "$PORT_FILE")
    fi
    echo -e "\033[1;36m"
    echo "         PROJET EXERGUE GLOBE — STATION DE TÉLÉMÉTRIE                   "
    echo -e "\033[0m"
    echo -e " [MANDAT]       : \033[1;33mSauf les dettes\033[0m"
    echo -e " [PORT ÉPHÉMÈRE]: \033[1;32m$ACTIVE_PORT\033[0m"
    echo -e " [MODE RÉSEAU]  : Mesh Telemetry"
    echo "------------------------------------------------------------------------"
    echo -e "\033[1;35m[CARTOGRAPHIE DES NŒUDS ACTIFS ET FLUX DE TÉLÉMÉTRIE]\033[0m"
    if [ -f "$LOG_FILE" ]; then
        tail -n 8 "$LOG_FILE"
    else
        echo " En attente d'initialisation du flux de télémétrie..."
    fi
    echo ""
    echo -e "\033[1;30m[Appuyez sur Ctrl+C pour détacher le terminal]\033[0m"
    sleep 2
done
EOF
chmod +x "$TARGET_DIR/core/extergobe_terminal.sh"

# 6. Lancement du service d'arrière-plan
echo -e "\033[1;32m[*] Amorçage du noyau...\033[0m"
"$TARGET_DIR/core/extergobe_space_core" &
sleep 1

echo -e "\033[1;32m"
echo "========================================================================"
echo "      PROJET EXERGUE GLOBE DÉPLOYÉ AVEC SUCCÈS (CLÉ EN MAIN)           "
echo "========================================================================"
echo " Mandat Exécutif : Sauf les dettes"
echo " Registre SHM    : $WORKSPACE/.network_port"
echo "========================================================================"
echo -e "\033[0m"

# 7. Exécution du terminal de cartographie
exec "$TARGET_DIR/core/extergobe_terminal.sh"
