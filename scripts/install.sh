#!/bin/bash
#
# LeuitCSS v1.0.0 - Installation Script
# Active Configuration Backup System with Read-Only Access
#
# Target OS: Ubuntu 24.04
# Deployment: Systemd service
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                    LeuitCSS v1.0.0                           ║"
echo "║        Active Configuration Backup System                     ║"
echo "║              Read-Only Device Access                          ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Check root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Please run as root or with sudo${NC}"
    exit 1
fi

# Configuration
INSTALL_DIR="/opt/leuitcss"
DATA_DIR="/var/lib/leuitcss"
LOG_DIR="/var/log/leuitcss"
CONFIG_DIR="/etc/leuitcss"
SERVICE_USER="leuitcss"
VENV_DIR="${INSTALL_DIR}/venv"
DEFAULT_PORT=5000
DEFAULT_FTP_PORT=2121

echo -e "${YELLOW}Step 1: Installing system dependencies...${NC}"
apt-get update -qq
apt-get install -y python3 python3-pip python3-venv python3-dev build-essential libffi-dev libssl-dev

echo -e "${YELLOW}Step 2: Creating system user...${NC}"
if ! id "$SERVICE_USER" &>/dev/null; then
    useradd --system --no-create-home --shell /bin/false $SERVICE_USER
    echo -e "${GREEN}Created user: ${SERVICE_USER}${NC}"
else
    echo -e "${GREEN}User ${SERVICE_USER} already exists${NC}"
fi

echo -e "${YELLOW}Step 3: Creating directories...${NC}"
mkdir -p $INSTALL_DIR
mkdir -p $DATA_DIR/{storage,data,ftp-ingestion/zte}
mkdir -p $LOG_DIR
mkdir -p $CONFIG_DIR

echo -e "${YELLOW}Step 4: Copying application files...${NC}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cp -r ${SCRIPT_DIR}/* $INSTALL_DIR/
rm -rf ${INSTALL_DIR}/scripts

echo -e "${YELLOW}Step 5: Configuring SSH for legacy network devices...${NC}"
# Many network devices (Huawei, ZTE, older Cisco) use ssh-rsa which is
# disabled by default in OpenSSH 8.8+ (Ubuntu 22.04+)
cat > /etc/ssh/ssh_config.d/leuitcss-legacy.conf << 'SSHCONF'
# LeuitCSS - Allow legacy SSH algorithms for network devices
Host *
    HostKeyAlgorithms +ssh-rsa,ssh-dss
    PubkeyAcceptedAlgorithms +ssh-rsa,ssh-dss
    KexAlgorithms +diffie-hellman-group14-sha1,diffie-hellman-group1-sha1
SSHCONF
chmod 644 /etc/ssh/ssh_config.d/leuitcss-legacy.conf
echo -e "${GREEN}SSH legacy algorithms enabled for network devices${NC}"

echo -e "${YELLOW}Step 6: Creating Python virtual environment...${NC}"
python3 -m venv $VENV_DIR
source $VENV_DIR/bin/activate

echo -e "${YELLOW}Step 7: Installing Python dependencies...${NC}"
pip install --upgrade pip wheel setuptools -q
pip install -r ${INSTALL_DIR}/requirements.txt

echo -e "${YELLOW}Step 8: Configuring FTP port capability...${NC}"
# ZTE OLT requires FTP on port 21 (cannot use custom port)
# Grant capability to bind to privileged ports without running as root
setcap 'cap_net_bind_service=+ep' ${VENV_DIR}/bin/python3.12 2>/dev/null || \
setcap 'cap_net_bind_service=+ep' ${VENV_DIR}/bin/python3 2>/dev/null || \
echo -e "${YELLOW}Note: Could not set CAP_NET_BIND_SERVICE. FTP on port 21 may require root.${NC}"
echo -e "${GREEN}FTP port 21 capability configured${NC}"

echo -e "${YELLOW}Step 9: Generating security keys...${NC}"
MASTER_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
FTP_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(16))")

echo -e "${YELLOW}Step 10: Creating configuration file...${NC}"

# Detect server IP
SERVER_IP=$(hostname -I | awk '{print $1}')

cat > ${CONFIG_DIR}/leuitcss.env << EOF
# LeuitCSS v1.0.0 Configuration
LEUITCSS_ENV=production
LEUITCSS_PORT=${DEFAULT_PORT}
LEUITCSS_SECRET_KEY=${SECRET_KEY}
LEUITCSS_MASTER_KEY=${MASTER_KEY}
LEUITCSS_DB_PATH=${DATA_DIR}/data/leuitcss.db
LEUITCSS_STORAGE_PATH=${DATA_DIR}/storage
LEUITCSS_LOG_PATH=${LOG_DIR}

# Server IP for FTP (used in ZTE backup command)
# Set this to the IP that network devices can reach
LEUITCSS_SERVER_IP=${SERVER_IP}

# FTP Ingestion Server (ZTE OLT only)
# Enable via Web UI: ZTE FTP Ingestion menu
# Port 21 required - ZTE OLT does not support custom FTP port
LEUITCSS_FTP_ENABLED=false
LEUITCSS_FTP_PORT=21
LEUITCSS_FTP_USER=leuitcss
LEUITCSS_FTP_PASSWORD=${FTP_PASSWORD}
LEUITCSS_FTP_ROOT=${DATA_DIR}/ftp-ingestion
EOF
chmod 600 ${CONFIG_DIR}/leuitcss.env

echo -e "${YELLOW}Step 11: Creating CLI wrapper...${NC}"
cat > /usr/local/bin/leuitcss << 'CLIWRAPPER'
#!/bin/bash
set -a
source /etc/leuitcss/leuitcss.env
set +a
cd /opt/leuitcss
/opt/leuitcss/venv/bin/python /opt/leuitcss/leuitcss-cli.py "$@"
CLIWRAPPER
chmod +x /usr/local/bin/leuitcss

echo -e "${YELLOW}Step 12: Testing application import...${NC}"
set -a
source ${CONFIG_DIR}/leuitcss.env
set +a

cd ${INSTALL_DIR}
TEST_RESULT=$(${VENV_DIR}/bin/python -c "
import sys
sys.path.insert(0, '${INSTALL_DIR}')
try:
    from main import app
    print('IMPORT_SUCCESS')
except Exception as e:
    print(f'IMPORT_FAILED: {e}')
" 2>&1)

if echo "$TEST_RESULT" | grep -q "IMPORT_SUCCESS"; then
    echo -e "${GREEN}Application import test: PASSED${NC}"
else
    echo -e "${RED}Application import test: FAILED${NC}"
    echo "$TEST_RESULT"
    exit 1
fi

echo -e "${YELLOW}Step 13: Creating systemd services...${NC}"

# Main LeuitCSS service
cat > /etc/systemd/system/leuitcss.service << EOF
[Unit]
Description=LeuitCSS - Active Configuration Backup System
After=network.target
Wants=leuitcss-ftp.service

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${INSTALL_DIR}
EnvironmentFile=${CONFIG_DIR}/leuitcss.env
ExecStart=${VENV_DIR}/bin/gunicorn --bind 0.0.0.0:${DEFAULT_PORT} --workers 2 --timeout 120 wsgi:application
Restart=always
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=${DATA_DIR} ${LOG_DIR}

[Install]
WantedBy=multi-user.target
EOF

# FTP Ingestion Service (for ZTE OLT)
# Runs as root to bind port 21
# This service is tightly coupled with main LeuitCSS service
cat > /etc/systemd/system/leuitcss-ftp.service << EOF
[Unit]
Description=LeuitCSS FTP Ingestion Server (ZTE OLT)
After=network.target
BindsTo=leuitcss.service
After=leuitcss.service

[Service]
Type=simple
ExecStart=${VENV_DIR}/bin/python ${INSTALL_DIR}/ftp-server.py
WorkingDirectory=${INSTALL_DIR}
EnvironmentFile=${CONFIG_DIR}/leuitcss.env
Restart=on-failure
RestartSec=5

# Security hardening
PrivateTmp=true
ProtectHome=true
ReadWritePaths=${DATA_DIR} ${LOG_DIR}

[Install]
WantedBy=leuitcss.service
EOF

echo -e "${GREEN}Systemd services created${NC}"

echo -e "${YELLOW}Step 14: Setting permissions...${NC}"
chown -R ${SERVICE_USER}:${SERVICE_USER} ${INSTALL_DIR}
chown -R ${SERVICE_USER}:${SERVICE_USER} ${DATA_DIR}
chown -R ${SERVICE_USER}:${SERVICE_USER} ${LOG_DIR}
chown -R root:${SERVICE_USER} ${CONFIG_DIR}
chmod 750 ${CONFIG_DIR}
# FTP directory needs to be writable
chmod 755 ${DATA_DIR}/ftp-ingestion
chmod 755 ${DATA_DIR}/ftp-ingestion/zte

# Sudoers for FTP service control via Web UI
cat > /etc/sudoers.d/leuitcss << 'SUDOERS'
# Allow leuitcss user to control FTP service without password
leuitcss ALL=(ALL) NOPASSWD: /bin/systemctl start leuitcss-ftp
leuitcss ALL=(ALL) NOPASSWD: /bin/systemctl stop leuitcss-ftp
leuitcss ALL=(ALL) NOPASSWD: /bin/systemctl restart leuitcss-ftp
leuitcss ALL=(ALL) NOPASSWD: /bin/systemctl status leuitcss-ftp
leuitcss ALL=(ALL) NOPASSWD: /usr/bin/systemctl start leuitcss-ftp
leuitcss ALL=(ALL) NOPASSWD: /usr/bin/systemctl stop leuitcss-ftp
leuitcss ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart leuitcss-ftp
leuitcss ALL=(ALL) NOPASSWD: /usr/bin/systemctl status leuitcss-ftp
SUDOERS
chmod 440 /etc/sudoers.d/leuitcss
echo -e "${GREEN}Sudoers configured for FTP control${NC}"

echo -e "${YELLOW}Step 15: Initializing database and admin account...${NC}"
cd ${INSTALL_DIR}
INIT_OUTPUT=$(${VENV_DIR}/bin/python leuitcss-cli.py init 2>&1)
echo "$INIT_OUTPUT"
ADMIN_PASSWORD=$(echo "$INIT_OUTPUT" | grep "Password:" | awk '{print $2}')

echo -e "${YELLOW}Step 16: Starting services...${NC}"
systemctl daemon-reload
systemctl enable leuitcss
systemctl start leuitcss

# FTP service - enable and start by default for ZTE OLT support
systemctl enable leuitcss-ftp
systemctl start leuitcss-ftp

sleep 3

if systemctl is-active --quiet leuitcss; then
    SERVICE_STATUS="${GREEN}RUNNING${NC}"
else
    SERVICE_STATUS="${RED}FAILED${NC}"
    echo -e "${RED}Service failed to start. Checking logs...${NC}"
    journalctl -u leuitcss -n 10 --no-pager
fi

if systemctl is-active --quiet leuitcss-ftp; then
    FTP_STATUS="${GREEN}ENABLED & RUNNING${NC}"
else
    FTP_STATUS="${YELLOW}STOPPED${NC}"
fi

SERVER_IP=$(hostname -I | awk '{print $1}')

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗"
echo -e "║              Installation Complete!                           ║"
echo -e "╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  WEB ACCESS"
echo "═══════════════════════════════════════════════════════════════"
echo "  URL: http://${SERVER_IP}:${DEFAULT_PORT}"
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  ADMIN CREDENTIALS"
echo "═══════════════════════════════════════════════════════════════"
echo "  Username: admin"
echo "  Password: ${ADMIN_PASSWORD}"
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  FTP INGESTION (ZTE OLT)"
echo "═══════════════════════════════════════════════════════════════"
echo -e "  Status:   ${FTP_STATUS}"
echo "  Port:     21 (fixed - ZTE OLT requirement)"
echo "  Username: leuitcss"
echo "  Password: ${FTP_PASSWORD}"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo -e "${RED}WARNING: Save these credentials NOW! Shown only once.${NC}"
echo ""
echo "Locations:"
echo "  App: ${INSTALL_DIR}"
echo "  Config: ${CONFIG_DIR}/leuitcss.env"
echo "  Database: ${DATA_DIR}/data/"
echo "  Backups: ${DATA_DIR}/storage/"
echo "  FTP Root: ${DATA_DIR}/ftp-ingestion/"
echo "  Logs: ${LOG_DIR}/"
echo ""
echo "Commands:"
echo "  leuitcss reset-password admin  - Reset admin password"
echo "  leuitcss status                - System status"
echo "  systemctl status leuitcss      - Service status"
echo "  journalctl -u leuitcss -f      - View logs"
echo ""
echo "Firewall:"
echo "  ufw allow ${DEFAULT_PORT}/tcp   # Web UI"
echo "  ufw allow 21/tcp                # FTP (ZTE OLT)"
echo ""
echo -e "Service Status: ${SERVICE_STATUS}"
echo ""
