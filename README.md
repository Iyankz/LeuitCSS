# LeuitCSS

**Leuit Config Storage System** — Immutable Network Configuration Storage

![Version](https://img.shields.io/badge/version-1.0.0-blue)
![Status](https://img.shields.io/badge/status-stable-green)
![Python](https://img.shields.io/badge/python-3.12-blue)
![Platform](https://img.shields.io/badge/platform-Ubuntu%2024.04-orange)
![License](https://img.shields.io/badge/license-MIT-green)

![Flask](https://img.shields.io/badge/flask-3.x-black)
![SQLite](https://img.shields.io/badge/database-SQLite-blue)
![Netmiko](https://img.shields.io/badge/netmiko-SSH%2FTelnet-lightgrey)

---

## What is "Leuit"?

**Leuit** (pronounced *leu-it*) is a traditional Sundanese rice granary from West Java, Indonesia. In Sundanese culture, the *leuit* is a sacred storage place where harvested rice is kept safe, untouched, and preserved for future use. The rice inside is never modified — only stored and retrieved when needed.

LeuitCSS applies this philosophy to network configuration management:

- **Configurations are valuable assets** — like rice sustaining a village
- **Storage is sacred and immutable** — no modifications, no deletions
- **Read-only access** — retrieve what you need, when you need it
- **The system is the source of truth** — append-only, verifiable history

---

## Features

- **Read-only backup collection** from network devices
- **Hardcoded backup commands** per vendor (no arbitrary command execution)
- **Immutable storage** with SHA-256 checksums
- **Scheduled backups** (daily, weekly, monthly)
- **Multi-vendor support**: MikroTik, Cisco, Huawei, ZTE, Juniper, Generic
- **SSH and Telnet** connections
- **ZTE OLT FTP ingestion** for `startrun.dat` files
- **Single admin** authentication
- **Web UI** for viewing and downloading backups
- **Server status monitoring** (read-only observability)
- **CLI tool** for password reset

---

## Supported Vendors

| Vendor | Connection | Backup Command |
|--------|------------|----------------|
| MikroTik | SSH | `/export` |
| Cisco | SSH / Telnet | `show running-config` |
| Huawei | SSH / Telnet | `display current-configuration` |
| ZTE OLT | Telnet + FTP | FTP upload `startrun.dat` |
| Juniper | SSH | `show configuration \| display set` |
| Generic | SSH / Telnet | `show running-config` |
| Generic (Saved) | SSH / Telnet | `show saved-config` |
| Generic (Startup) | SSH / Telnet | `show startup-config` |

---

## Generic Vendors

LeuitCSS menyediakan 3 varian **Generic** untuk mendukung berbagai perangkat dengan CLI mirip Cisco yang menggunakan command berbeda untuk backup konfigurasi:

### Generic (Running Config)

```
Command: show running-config
```

Gunakan untuk perangkat yang menampilkan konfigurasi aktif dengan command `show running-config`.

**Perangkat yang didukung:**
- DCN Switches
- Whitebox/unbranded switches
- OEM network devices
- Perangkat dengan CLI mirip Cisco IOS

### Generic (Saved Config)

```
Command: show saved-config
```

Gunakan untuk perangkat yang menyimpan konfigurasi tersimpan secara terpisah dan menggunakan command `show saved-config`.

**Perangkat yang didukung:**
- Beberapa switch managed layer 2/3
- Perangkat yang membedakan running vs saved config
- Legacy switches dengan command non-standard

### Generic (Startup Config)

```
Command: show startup-config
```

Gunakan untuk perangkat yang menggunakan command `show startup-config` untuk menampilkan konfigurasi yang akan dimuat saat boot.

**Perangkat yang didukung:**
- Cisco-compatible devices
- Beberapa switch enterprise
- Perangkat dengan NVRAM-based config

### Cara Memilih Generic Vendor

| Jika perangkat menggunakan... | Pilih vendor... |
|-------------------------------|-----------------|
| `show running-config` | Generic |
| `show saved-config` | Generic (Saved) |
| `show startup-config` | Generic (Startup) |

> **Catatan:** Semua varian Generic menggunakan device type `cisco_ios` dari Netmiko untuk kompatibilitas CLI.

---

## Requirements

- Ubuntu 24.04 LTS
- Python 3.12
- Network access to target devices

---

## Installation

```bash
# Extract package
unzip LeuitCSS-v1.0.0.zip -d ~/leuitcss
cd ~/leuitcss

# Run installer
sudo bash scripts/install.sh
```

The installer will:
1. Create system user `leuitcss`
2. Install to `/opt/leuitcss`
3. Setup Python virtual environment
4. Configure systemd service
5. Generate encryption key
6. Configure SSH for legacy devices

After installation, access the web UI at `http://your-server:5000`

---

## Configuration

Edit `/etc/leuitcss/leuitcss.env` to customize:

```ini
# Environment
LEUITCSS_ENV=production

# Server
LEUITCSS_PORT=5000

# Security (auto-generated during install)
LEUITCSS_SECRET_KEY=your-secret-key
LEUITCSS_MASTER_KEY=your-master-key

# Paths
LEUITCSS_DB_PATH=/var/lib/leuitcss/data/leuitcss.db
LEUITCSS_STORAGE_PATH=/var/lib/leuitcss/storage
LEUITCSS_LOG_PATH=/var/log/leuitcss
```

---

## ZTE OLT FTP Ingestion

LeuitCSS includes a built-in FTP server for ZTE OLT backup ingestion. The FTP service runs automatically alongside the main LeuitCSS service.

### FTP Service

- **Port:** 21 (fixed - ZTE OLT requirement)
- **Status:** Always running with LeuitCSS
- **User:** leuitcss (configured in .env)

The FTP server starts automatically when LeuitCSS starts and stops when LeuitCSS stops. No manual enable/disable required.

### FTP Credentials

FTP credentials are configured in `/etc/leuitcss/leuitcss.env`:

```ini
LEUITCSS_FTP_USER=leuitcss
LEUITCSS_FTP_PASSWORD=<auto-generated-during-install>
LEUITCSS_FTP_ROOT=/var/lib/leuitcss/ftp-ingestion
```

### How ZTE Backup Works

1. LeuitCSS connects to ZTE OLT via Telnet
2. Sends FTP upload command with LeuitCSS server IP
3. ZTE OLT uploads `startrun.dat` to FTP server
4. LeuitCSS polls for file and stores to immutable storage

### FTP Upload Structure

ZTE uploads to:

```
/ftp-root/zte/
  OLT-CORE-01/
    startrun.dat
  OLT-CORE-02/
    startrun.dat
```

### FTP Security

- **Write-only**: Cannot read, list, or delete files
- **Single credential**: One global FTP account for all ZTE devices
- **File validation**: Only accepts `startrun.dat`
- **ZTE only**: Other vendors use SSH/Telnet

### Server IP Configuration

Set the LeuitCSS server IP that ZTE OLT can reach in `/etc/leuitcss/leuitcss.env`:

```ini
LEUITCSS_SERVER_IP=192.168.1.100
```

This IP is used in the FTP upload command sent to ZTE OLT.

---

## CLI Commands

```bash
# Reset admin password
sudo leuitcss reset-password admin

# View system status
sudo leuitcss status

# View service status
sudo systemctl status leuitcss

# View logs
sudo journalctl -u leuitcss -f
```

---

## Web UI Pages

| Page | Description |
|------|-------------|
| Dashboard | Overview, recent backups, server time |
| Devices | List and manage devices |
| Schedules | Backup schedules (daily/weekly/monthly) |
| Backups | Backup history with download |
| Statistics | Backup statistics by vendor/device |
| Server Status | System observability (read-only) |

---

## Security Considerations

- **Credentials are encrypted** using AES-256 before storage
- **Backup files are checksummed** with SHA-256
- **No configuration push** — system is read-only by design
- **No arbitrary commands** — only hardcoded backup commands
- **Single admin account** — no multi-user complexity
- **Audit logging** of all actions
- **FTP write-only** — no read or delete capability

---

## Uninstall

```bash
sudo bash /opt/leuitcss/scripts/uninstall.sh
```

---

## License

MIT License — see [LICENSE](LICENSE) file.

---

## Author

**Iyankz and Brother**

- Website: [iyankz.github.io](https://iyankz.github.io)
- GitHub: [github.com/Iyankz/LeuitCSS](https://github.com/Iyankz/LeuitCSS)
