#!/bin/bash
#
# LeuitCSS Hotfix - Add FTP Configuration for ZTE OLT
# Untuk instalasi yang sudah ada
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║       LeuitCSS Hotfix - FTP Configuration (ZTE OLT)          ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Check root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Please run as root or with sudo${NC}"
    exit 1
fi

CONFIG_FILE="/etc/leuitcss/leuitcss.env"
DATA_DIR="/var/lib/leuitcss"
VENV_DIR="/opt/leuitcss/venv"

# Check if config exists
if [ ! -f "$CONFIG_FILE" ]; then
    echo -e "${RED}Config file not found: $CONFIG_FILE${NC}"
    echo "Please run full installation first."
    exit 1
fi

# Check if FTP config already exists
if grep -q "LEUITCSS_FTP_ENABLED" "$CONFIG_FILE"; then
    echo -e "${YELLOW}FTP configuration already exists in $CONFIG_FILE${NC}"
    echo ""
    echo "Current FTP settings:"
    grep "LEUITCSS_FTP" "$CONFIG_FILE"
    echo ""
    read -p "Do you want to regenerate FTP password? (y/N): " REGEN
    if [[ "$REGEN" =~ ^[Yy]$ ]]; then
        FTP_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(16))")
        sed -i "s/^LEUITCSS_FTP_PASSWORD=.*/LEUITCSS_FTP_PASSWORD=${FTP_PASSWORD}/" "$CONFIG_FILE"
        # Also update port to 21 if not already
        sed -i "s/^LEUITCSS_FTP_PORT=.*/LEUITCSS_FTP_PORT=21/" "$CONFIG_FILE"
        echo -e "${GREEN}FTP password regenerated.${NC}"
        echo ""
        echo "═══════════════════════════════════════════════════════════════"
        echo "  NEW FTP PASSWORD"
        echo "═══════════════════════════════════════════════════════════════"
        echo "  Password: ${FTP_PASSWORD}"
        echo "═══════════════════════════════════════════════════════════════"
        echo ""
        echo -e "${RED}WARNING: Save this password NOW! Shown only once.${NC}"
        
        # Restart service
        echo ""
        echo "Restarting service..."
        systemctl restart leuitcss
        sleep 2
        
        if systemctl is-active --quiet leuitcss; then
            echo -e "${GREEN}Service restarted successfully.${NC}"
        else
            echo -e "${RED}Service failed to restart. Check logs.${NC}"
        fi
    fi
    exit 0
fi

echo -e "${YELLOW}Adding FTP configuration...${NC}"

# Generate FTP password
FTP_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(16))")

# Create FTP directory structure
echo "Creating FTP directory structure..."
mkdir -p ${DATA_DIR}/ftp-ingestion/zte
chown -R leuitcss:leuitcss ${DATA_DIR}/ftp-ingestion

# Set CAP_NET_BIND_SERVICE for port 21
echo "Configuring port 21 capability..."
setcap 'cap_net_bind_service=+ep' ${VENV_DIR}/bin/python3.12 2>/dev/null || \
setcap 'cap_net_bind_service=+ep' ${VENV_DIR}/bin/python3 2>/dev/null || \
echo -e "${YELLOW}Note: Could not set CAP_NET_BIND_SERVICE.${NC}"

# Add FTP config to env file
echo "" >> "$CONFIG_FILE"
cat >> "$CONFIG_FILE" << EOF

# FTP Ingestion Server (ZTE OLT only)
# Enable via Web UI: ZTE FTP Ingestion menu
# Port 21 is REQUIRED - ZTE OLT does not support custom FTP port
LEUITCSS_FTP_ENABLED=false
LEUITCSS_FTP_PORT=21
LEUITCSS_FTP_USER=leuitcss
LEUITCSS_FTP_PASSWORD=${FTP_PASSWORD}
LEUITCSS_FTP_ROOT=${DATA_DIR}/ftp-ingestion
EOF

echo -e "${GREEN}FTP configuration added.${NC}"

# Restart service
echo ""
echo "Restarting service..."
systemctl restart leuitcss
sleep 2

if systemctl is-active --quiet leuitcss; then
    SERVICE_STATUS="${GREEN}RUNNING${NC}"
else
    SERVICE_STATUS="${RED}FAILED${NC}"
fi

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗"
echo -e "║              FTP Configuration Complete!                      ║"
echo -e "╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  FTP INGESTION (ZTE OLT)"
echo "═══════════════════════════════════════════════════════════════"
echo "  Status:   DISABLED (enable via Web UI)"
echo "  Port:     21 (fixed - ZTE OLT requirement)"
echo "  Username: leuitcss"
echo "  Password: ${FTP_PASSWORD}"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo -e "${RED}WARNING: Save this password NOW! Shown only once.${NC}"
echo ""
echo "To enable FTP:"
echo "  1. Open Web UI"
echo "  2. Go to: ZTE FTP Ingestion"
echo "  3. Toggle 'Enable FTP Server'"
echo "  4. Click 'Save Settings'"
echo ""
echo "Firewall (when FTP enabled):"
echo "  ufw allow 21/tcp"
echo ""
echo -e "Service Status: ${SERVICE_STATUS}"
echo ""
