#!/usr/bin/env bash
# Idempotent installer for mcp39f511n-logger on Debian/Ubuntu.
# Run as root: sudo ./deploy/install.sh
set -euo pipefail

INSTALL_DIR="/opt/mcp39f511n-logger"
LOG_DIR="/var/log/mcp39f511n"
CONFIG_DIR="/etc/mcp39f511n-logger"
SERVICE_NAME="mcp39f511n-logger"
SERVICE_USER="mcp39f511n"
UNIT_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

# Resolve script directory so we can reference sibling files
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "${SCRIPT_DIR}")"

if [[ "${EUID}" -ne 0 ]]; then
    echo "ERROR: This script must be run as root (sudo)." >&2
    exit 1
fi

echo "==> Checking Python version..."
python3_bin="$(command -v python3 || true)"
if [[ -z "${python3_bin}" ]]; then
    echo "ERROR: python3 not found. Install with: apt install python3 python3-venv" >&2
    exit 1
fi
python3_version="$("${python3_bin}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
python3_major="$(echo "${python3_version}" | cut -d. -f1)"
python3_minor="$(echo "${python3_version}" | cut -d. -f2)"
if [[ "${python3_major}" -lt 3 ]] || { [[ "${python3_major}" -eq 3 ]] && [[ "${python3_minor}" -lt 10 ]]; }; then
    echo "ERROR: Python >= 3.10 required; found ${python3_version}." >&2
    exit 1
fi
echo "    Python ${python3_version} OK"

echo "==> Creating system user '${SERVICE_USER}'..."
if ! id "${SERVICE_USER}" &>/dev/null; then
    useradd --system --no-create-home --shell /usr/sbin/nologin "${SERVICE_USER}"
    echo "    Created user '${SERVICE_USER}'"
else
    echo "    User '${SERVICE_USER}' already exists"
fi

echo "==> Adding '${SERVICE_USER}' to 'dialout' group..."
usermod -aG dialout "${SERVICE_USER}"
echo "    Done"

echo "==> Creating directories..."
install -d -o root -g root -m 755 "${INSTALL_DIR}"
install -d -o "${SERVICE_USER}" -g "${SERVICE_USER}" -m 755 "${LOG_DIR}"
install -d -o root -g root -m 755 "${CONFIG_DIR}"
echo "    Done"

echo "==> Syncing source files to ${INSTALL_DIR}..."
rsync -a --delete \
    --exclude='.venv' \
    --exclude='__pycache__' \
    --exclude='*.egg-info' \
    --exclude='.git' \
    --exclude='*.csv' \
    "${REPO_ROOT}/" "${INSTALL_DIR}/"
chown -R root:root "${INSTALL_DIR}"
echo "    Done"

echo "==> Creating Python virtual environment..."
if [[ ! -d "${INSTALL_DIR}/.venv" ]]; then
    "${python3_bin}" -m venv "${INSTALL_DIR}/.venv"
    echo "    Created .venv"
else
    echo "    .venv already exists"
fi

echo "==> Installing package into venv..."
"${INSTALL_DIR}/.venv/bin/pip" install --quiet --upgrade pip
"${INSTALL_DIR}/.venv/bin/pip" install --quiet "${INSTALL_DIR}"
echo "    Done"

echo "==> Installing systemd unit..."
install -o root -g root -m 644 "${SCRIPT_DIR}/mcp39f511n-logger.service" "${UNIT_FILE}"
echo "    Installed ${UNIT_FILE}"

echo "==> Installing default config (if not present)..."
if [[ ! -f "${CONFIG_DIR}/config.yaml" ]]; then
    install -o root -g root -m 644 "${SCRIPT_DIR}/config.example.yaml" "${CONFIG_DIR}/config.yaml"
    echo "    Installed default config to ${CONFIG_DIR}/config.yaml"
else
    echo "    Config already exists at ${CONFIG_DIR}/config.yaml — not overwritten"
fi

echo "==> Running systemctl daemon-reload..."
systemctl daemon-reload
echo "    Done"

echo ""
echo "============================================================"
echo " Installation complete!"
echo "============================================================"
echo ""
echo "Next steps:"
echo "  1. Edit the config:   sudo \${EDITOR:-nano} ${CONFIG_DIR}/config.yaml"
echo "     (Set 'serial.port' to your device, e.g. /dev/ttyUSB0)"
echo ""
echo "  2. Enable and start:  sudo systemctl enable --now ${SERVICE_NAME}"
echo ""
echo "  3. Watch logs:        journalctl -u ${SERVICE_NAME} -f"
echo "     CSV output:        ls ${LOG_DIR}/"
echo ""
echo "To stop and disable:  sudo systemctl disable --now ${SERVICE_NAME}"
