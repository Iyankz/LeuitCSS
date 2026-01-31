#!/bin/bash
#
# LeuitCSS Hotfix - Setup FTP Service for ZTE OLT
# Creates leuitcss-ftp.service as separate systemd service
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║     LeuitCSS Hotfix - FTP Service Setup (ZTE OLT)            ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Check root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Please run as root or with sudo${NC}"
    exit 1
fi

INSTALL_DIR="/opt/leuitcss"
DATA_DIR="/var/lib/leuitcss"
LOG_DIR="/var/log/leuitcss"
CONFIG_DIR="/etc/leuitcss"
VENV_DIR="${INSTALL_DIR}/venv"

# Check if LeuitCSS is installed
if [ ! -d "$INSTALL_DIR" ]; then
    echo -e "${RED}LeuitCSS not found at $INSTALL_DIR${NC}"
    exit 1
fi

echo -e "${YELLOW}Step 1: Creating FTP server script...${NC}"
cat > ${INSTALL_DIR}/ftp-server.py << 'FTPSCRIPT'
#!/usr/bin/env python3
"""
LeuitCSS v1.0.0 - Standalone FTP Ingestion Server
Write-only FTP server for ZTE OLT backup file ingestion
"""

import os
import sys
import logging
import signal
from pathlib import Path
from datetime import datetime

sys.path.insert(0, '/opt/leuitcss')

try:
    from dotenv import load_dotenv
    load_dotenv('/etc/leuitcss/leuitcss.env')
except:
    pass

try:
    from pyftpdlib.authorizers import DummyAuthorizer
    from pyftpdlib.handlers import FTPHandler
    from pyftpdlib.servers import FTPServer
except ImportError:
    print("ERROR: pyftpdlib not installed")
    sys.exit(1)

FTP_PORT = int(os.environ.get('LEUITCSS_FTP_PORT', '21'))
FTP_USER = os.environ.get('LEUITCSS_FTP_USER', 'leuitcss')
FTP_PASSWORD = os.environ.get('LEUITCSS_FTP_PASSWORD', '')
FTP_ROOT = os.environ.get('LEUITCSS_FTP_ROOT', '/var/lib/leuitcss/ftp-ingestion')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/var/log/leuitcss/ftp-server.log')
    ]
)
logger = logging.getLogger('leuitcss.ftp')

class LeuitFTPHandler(FTPHandler):
    def on_file_received(self, file):
        logger.info(f"File received: {file}")
        if not file.endswith('startrun.dat'):
            logger.warning(f"Ignoring non-startrun.dat file: {file}")
            return
        logger.info(f"ZTE config file received: {file}")
    
    def on_incomplete_file_received(self, file):
        logger.warning(f"Incomplete file upload: {file}")
        try:
            os.remove(file)
        except:
            pass

def setup_directories():
    ftp_path = Path(FTP_ROOT)
    zte_path = ftp_path / 'zte'
    ftp_path.mkdir(parents=True, exist_ok=True)
    zte_path.mkdir(exist_ok=True)
    os.chmod(ftp_path, 0o755)
    os.chmod(zte_path, 0o755)
    logger.info(f"FTP directories ready: {ftp_path}")

def create_status_file(status, port=FTP_PORT):
    status_file = Path('/var/lib/leuitcss/ftp-server.status')
    try:
        with open(status_file, 'w') as f:
            f.write(f"status={status}\n")
            f.write(f"port={port}\n")
            f.write(f"timestamp={datetime.now().isoformat()}\n")
            f.write(f"pid={os.getpid()}\n")
        os.chmod(status_file, 0o644)
    except Exception as e:
        logger.error(f"Failed to create status file: {e}")

def remove_status_file():
    status_file = Path('/var/lib/leuitcss/ftp-server.status')
    try:
        if status_file.exists():
            status_file.unlink()
    except:
        pass

def main():
    if not FTP_PASSWORD:
        logger.error("FTP password not configured")
        sys.exit(1)
    
    logger.info(f"Starting LeuitCSS FTP Server on port {FTP_PORT}")
    setup_directories()
    
    authorizer = DummyAuthorizer()
    authorizer.add_user(FTP_USER, FTP_PASSWORD, FTP_ROOT, perm='emw')
    
    handler = LeuitFTPHandler
    handler.authorizer = authorizer
    handler.passive_ports = range(60000, 60100)
    handler.banner = "LeuitCSS FTP Ingestion Server - ZTE OLT Only"
    
    server = FTPServer(('0.0.0.0', FTP_PORT), handler)
    server.max_cons = 10
    server.max_cons_per_ip = 3
    
    def signal_handler(signum, frame):
        logger.info("Shutting down FTP server...")
        remove_status_file()
        server.close_all()
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    create_status_file('running', FTP_PORT)
    logger.info(f"FTP Server started on port {FTP_PORT}")
    
    try:
        server.serve_forever()
    except Exception as e:
        logger.error(f"FTP Server error: {e}")
        create_status_file('error', FTP_PORT)
        sys.exit(1)
    finally:
        remove_status_file()

if __name__ == '__main__':
    main()
FTPSCRIPT

chmod +x ${INSTALL_DIR}/ftp-server.py
chown leuitcss:leuitcss ${INSTALL_DIR}/ftp-server.py
echo -e "${GREEN}FTP server script created${NC}"

echo -e "${YELLOW}Step 2: Creating systemd service for FTP...${NC}"
cat > /etc/systemd/system/leuitcss-ftp.service << EOF
[Unit]
Description=LeuitCSS FTP Ingestion Server (ZTE OLT)
After=network.target
PartOf=leuitcss.service

[Service]
Type=simple
ExecStart=${VENV_DIR}/bin/python ${INSTALL_DIR}/ftp-server.py
WorkingDirectory=${INSTALL_DIR}
EnvironmentFile=${CONFIG_DIR}/leuitcss.env
Restart=on-failure
RestartSec=5
PrivateTmp=true
ProtectHome=true
ReadWritePaths=${DATA_DIR} ${LOG_DIR}

[Install]
WantedBy=multi-user.target
EOF

echo -e "${GREEN}Systemd service created${NC}"

echo -e "${YELLOW}Step 3: Setting up FTP directories...${NC}"
mkdir -p ${DATA_DIR}/ftp-ingestion/zte
chown -R leuitcss:leuitcss ${DATA_DIR}/ftp-ingestion
chmod 755 ${DATA_DIR}/ftp-ingestion
chmod 755 ${DATA_DIR}/ftp-ingestion/zte
echo -e "${GREEN}FTP directories created${NC}"

echo -e "${YELLOW}Step 4: Checking FTP configuration...${NC}"
CONFIG_FILE="${CONFIG_DIR}/leuitcss.env"

if ! grep -q "LEUITCSS_FTP_ENABLED" "$CONFIG_FILE"; then
    echo "Adding FTP configuration to .env..."
    FTP_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(16))")
    
    cat >> "$CONFIG_FILE" << EOF

# FTP Ingestion Server (ZTE OLT only)
# Port 21 is REQUIRED - ZTE OLT does not support custom FTP port
LEUITCSS_FTP_ENABLED=false
LEUITCSS_FTP_PORT=21
LEUITCSS_FTP_USER=leuitcss
LEUITCSS_FTP_PASSWORD=${FTP_PASSWORD}
LEUITCSS_FTP_ROOT=${DATA_DIR}/ftp-ingestion
EOF
    echo -e "${GREEN}FTP configuration added${NC}"
    echo ""
    echo "═══════════════════════════════════════════════════════════════"
    echo "  FTP CREDENTIALS"
    echo "═══════════════════════════════════════════════════════════════"
    echo "  Username: leuitcss"
    echo "  Password: ${FTP_PASSWORD}"
    echo "═══════════════════════════════════════════════════════════════"
    echo ""
    echo -e "${RED}WARNING: Save this password NOW! Shown only once.${NC}"
else
    echo -e "${GREEN}FTP configuration already exists${NC}"
    # Update port to 21 if different
    sed -i 's/^LEUITCSS_FTP_PORT=.*/LEUITCSS_FTP_PORT=21/' "$CONFIG_FILE"
fi

echo -e "${YELLOW}Step 5: Configuring sudoers for FTP control...${NC}"
cat > /etc/sudoers.d/leuitcss-ftp << 'SUDOERS'
# Allow leuitcss user to control FTP service
leuitcss ALL=(ALL) NOPASSWD: /bin/systemctl start leuitcss-ftp
leuitcss ALL=(ALL) NOPASSWD: /bin/systemctl stop leuitcss-ftp
leuitcss ALL=(ALL) NOPASSWD: /bin/systemctl restart leuitcss-ftp
leuitcss ALL=(ALL) NOPASSWD: /bin/systemctl status leuitcss-ftp
SUDOERS
chmod 440 /etc/sudoers.d/leuitcss-ftp
echo -e "${GREEN}Sudoers configured${NC}"

echo -e "${YELLOW}Step 6: Reloading systemd...${NC}"
systemctl daemon-reload
systemctl enable leuitcss-ftp
echo -e "${GREEN}Systemd reloaded${NC}"

echo -e "${YELLOW}Step 7: Restarting LeuitCSS main service...${NC}"
systemctl restart leuitcss
sleep 2

if systemctl is-active --quiet leuitcss; then
    MAIN_STATUS="${GREEN}RUNNING${NC}"
else
    MAIN_STATUS="${RED}FAILED${NC}"
fi

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗"
echo -e "║              FTP Service Setup Complete!                      ║"
echo -e "╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo "FTP Service: leuitcss-ftp.service"
echo "FTP Port:    21 (fixed - ZTE OLT requirement)"
echo "FTP Root:    ${DATA_DIR}/ftp-ingestion/"
echo ""
echo "To enable FTP:"
echo "  1. Open Web UI -> ZTE FTP Ingestion"
echo "  2. Toggle 'Enable FTP Server'"
echo "  3. Click 'Save Settings'"
echo ""
echo "Or via command line:"
echo "  sudo systemctl start leuitcss-ftp"
echo "  sudo systemctl stop leuitcss-ftp"
echo ""
echo "Firewall (when FTP enabled):"
echo "  ufw allow 21/tcp"
echo ""
echo -e "LeuitCSS Main Service: ${MAIN_STATUS}"
echo ""
