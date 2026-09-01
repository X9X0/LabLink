#!/bin/bash
# LabLink first-run setup.
#
# Raspberry Pi OS runs this once, as root, very early in the first boot -
# invoked by systemd.run= in cmdline.txt, which the image builder appends.
#
# It runs BEFORE the network is up, so it deliberately does no downloading.
# Everything network-dependent is handled by lablink-first-boot.service, which
# this script installs and which waits for network-online.target on the next
# boot. Keeping that split is what lets the image be built without root on any
# platform: no ext4 write access is needed at build time.
#
# Placeholders written in double-underscore form are substituted by the builder.
set +e

BOOT_DIR=/boot/firmware
[ -d "$BOOT_DIR" ] || BOOT_DIR=/boot

# Log to the boot partition, not /var/log. If the Pi fails to come up, this is
# the only forensic trail, and it has to be readable by whoever built the
# image - who may well be on Windows, where the ext4 root filesystem is not
# readable at all but this FAT partition mounts as a normal drive.
LOG="$BOOT_DIR/lablink-firstrun.log"
exec >> "$LOG" 2>&1

echo "[LabLink] first-run setup starting at $(date)"

# --- hostname -------------------------------------------------------------
NEW_HOSTNAME='__LABLINK_HOSTNAME__'
if [ -n "$NEW_HOSTNAME" ]; then
    CURRENT=$(cat /etc/hostname 2>/dev/null | tr -d '[:space:]')
    echo "$NEW_HOSTNAME" > /etc/hostname
    sed -i "s/127.0.1.1.*$CURRENT/127.0.1.1\t$NEW_HOSTNAME/g" /etc/hosts 2>/dev/null
    hostnamectl set-hostname "$NEW_HOSTNAME" 2>/dev/null
    echo "[LabLink] hostname set to $NEW_HOSTNAME"
fi

# --- wifi ------------------------------------------------------------------
# Written as a NetworkManager connection: Bookworm and later use NM, and the
# legacy wpa_supplicant.conf path is ignored there.
WIFI_SSID='__WIFI_SSID__'
WIFI_PASSWORD='__WIFI_PASSWORD__'
WIFI_COUNTRY='__WIFI_COUNTRY__'
if [ -n "$WIFI_SSID" ]; then
    mkdir -p /etc/NetworkManager/system-connections
    # A fixed filename: an SSID may contain a slash or other characters that
    # are not valid in a path, and NetworkManager takes the network name from
    # the ssid= field below rather than from the filename.
    CONN="/etc/NetworkManager/system-connections/lablink-wifi.nmconnection"
    cat > "$CONN" <<NMEOF
[connection]
id=${WIFI_SSID}
type=wifi
autoconnect=true
autoconnect-priority=100

[wifi]
mode=infrastructure
ssid=${WIFI_SSID}

[wifi-security]
key-mgmt=wpa-psk
psk=${WIFI_PASSWORD}

[ipv4]
method=auto

[ipv6]
method=auto
NMEOF
    chmod 600 "$CONN"
    [ -n "$WIFI_COUNTRY" ] && raspi-config nonint do_wifi_country "$WIFI_COUNTRY" 2>/dev/null
    rfkill unblock wifi 2>/dev/null
    echo "[LabLink] wifi configured for SSID $WIFI_SSID"
fi

# --- admin account ---------------------------------------------------------
# Create the account here rather than leaving it to userconfig.service, which
# reads userconf.txt on the *next* boot. Recent Raspberry Pi OS ships with no
# user at all, so at this point in the first boot there is nothing to add
# groups to - and silently skipping that would cost us dialout, which is what
# USB serial instruments need. This is what Raspberry Pi Imager does too.
ADMIN_USER='__ADMIN_USER__'
if [ -n "$ADMIN_USER" ] && ! id "$ADMIN_USER" >/dev/null 2>&1; then
    ADMIN_HASH=$(head -n1 "$BOOT_DIR/userconf.txt" 2>/dev/null | cut -d: -f2-)
    if [ -n "$ADMIN_HASH" ]; then
        if [ -x /usr/lib/userconf-pi/userconf ]; then
            # Renames the stock first user if there is one, creates it if not.
            /usr/lib/userconf-pi/userconf "$ADMIN_USER" "$ADMIN_HASH"
        else
            useradd -m -s /bin/bash "$ADMIN_USER" 2>/dev/null
            echo "$ADMIN_USER:$ADMIN_HASH" | chpasswd -e
        fi
        echo "[LabLink] admin account $ADMIN_USER created"
    else
        echo "[LabLink] WARNING: no userconf.txt hash; account not created here"
    fi
fi

if id "$ADMIN_USER" >/dev/null 2>&1; then
    # One group at a time: usermod aborts the whole call if any single group
    # is missing, and gpio/i2c/spi are not present on every Pi OS variant. A
    # missing gpio group must not cost us dialout.
    for grp in sudo adm dialout plugdev netdev video i2c spi gpio; do
        getent group "$grp" >/dev/null 2>&1 && usermod -aG "$grp" "$ADMIN_USER" 2>/dev/null
    done
    echo "$ADMIN_USER ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/010_lablink-nopasswd
    chmod 0440 /etc/sudoers.d/010_lablink-nopasswd
    echo "[LabLink] $ADMIN_USER added to instrument and admin groups"

    # The hash has done its job. Leaving it means a password hash sits on a
    # FAT partition that mounts on any machine the card is plugged into.
    rm -f "$BOOT_DIR/userconf.txt"
else
    echo "[LabLink] WARNING: $ADMIN_USER does not exist; leaving userconf.txt"
fi

# --- staged admin password for the application -----------------------------
# Written root-only and consumed (then deleted) by lablink-first-boot.sh.
if [ -f "$BOOT_DIR/lablink-admin-password" ]; then
    install -m 600 "$BOOT_DIR/lablink-admin-password" /etc/lablink-build-admin-password
    rm -f "$BOOT_DIR/lablink-admin-password"
    echo "[LabLink] admin password staged for the application"
fi

# --- install the network-dependent stage -----------------------------------
if [ -f "$BOOT_DIR/lablink-first-boot.sh" ]; then
    install -m 755 "$BOOT_DIR/lablink-first-boot.sh" /usr/local/bin/lablink-first-boot.sh
    rm -f "$BOOT_DIR/lablink-first-boot.sh"
fi

cat > /etc/systemd/system/lablink-first-boot.service <<'UNIT'
[Unit]
Description=LabLink First Boot Setup
After=network-online.target multi-user.target
Wants=network-online.target
ConditionPathExists=!/var/lib/lablink-setup-complete

[Service]
Type=oneshot
ExecStart=/usr/local/bin/lablink-first-boot.sh
RemainAfterExit=yes
StandardOutput=journal+console
StandardError=journal+console
TimeoutStartSec=3600

[Install]
WantedBy=multi-user.target
UNIT
systemctl enable lablink-first-boot.service 2>/dev/null
echo "[LabLink] lablink-first-boot.service installed and enabled"

# --- remove ourselves from cmdline.txt so this runs exactly once -----------
CMDLINE="$BOOT_DIR/cmdline.txt"
if [ -f "$CMDLINE" ]; then
    sed -i 's| systemd\.run=[^ ]*||g; s| systemd\.run_success_action=[^ ]*||g; s| systemd\.unit=[^ ]*||g' "$CMDLINE"
    echo "[LabLink] cmdline.txt restored"
fi

echo "[LabLink] first-run setup complete; rebooting into normal boot"
sync

# systemd.run_success_action=reboot only fires on a zero exit. Anything else
# leaves the Pi parked in kernel-command-line.target with no multi-user and no
# SSH - unreachable, and indistinguishable from a dead card. This script is
# best-effort throughout (set +e), so say so explicitly.
exit 0
