#!/bin/bash
#
# LeuitCSS v1.0.0 - Uninstall Script
#

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${RED}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║              LeuitCSS Uninstaller                            ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Please run as root or with sudo${NC}"
    exit 1
fi

INSTALL_DIR="/opt/leuitcss"
DATA_DIR="/var/lib/leuitcss"
LOG_DIR="/var/log/leuitcss"
CONFIG_DIR="/etc/leuitcss"
SERVICE_USER="leuitcss"

read -p "This will remove LeuitCSS and ALL data. Are you sure? (yes/no): " confirm
if [ "$confirm" != "yes" ]; then
    echo "Aborted."
    exit 0
fi

echo -e "${YELLOW}Stopping service...${NC}"
systemctl stop leuitcss 2>/dev/null || true
systemctl disable leuitcss 2>/dev/null || true

echo -e "${YELLOW}Removing systemd service...${NC}"
rm -f /etc/systemd/system/leuitcss.service
systemctl daemon-reload

echo -e "${YELLOW}Removing directories...${NC}"
rm -rf $INSTALL_DIR
rm -rf $LOG_DIR
rm -rf $CONFIG_DIR

read -p "Remove all backup data? (yes/no): " remove_data
if [ "$remove_data" == "yes" ]; then
    rm -rf $DATA_DIR
    echo -e "${GREEN}Data directory removed${NC}"
else
    echo -e "${YELLOW}Data preserved at ${DATA_DIR}${NC}"
fi

echo -e "${YELLOW}Removing system user...${NC}"
userdel $SERVICE_USER 2>/dev/null || true

echo -e "${GREEN}LeuitCSS has been uninstalled.${NC}"
