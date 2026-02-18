# SSH & Firewall Hardening Guide

Comprehensive guide for hardening SSH, firewall, and tunnel configurations.
Integrates with the OpenClaw `ssh_hardening` skill for guided, auditable execution.

---

## 1. SSH Configuration Hardening

### 1.1 Disable Root Login

```bash
# /etc/ssh/sshd_config
PermitRootLogin no
```

### 1.2 Key-Only Authentication

Ensure at least one authorized key exists **before** disabling password auth:

```bash
# Verify keys exist
ls -la ~/.ssh/authorized_keys

# /etc/ssh/sshd_config
PasswordAuthentication no
PubkeyAuthentication yes
ChallengeResponseAuthentication no
```

### 1.3 Strong Ciphers and MACs

```bash
# /etc/ssh/sshd_config
Ciphers chacha20-poly1305@openssh.com,aes256-gcm@openssh.com,aes128-gcm@openssh.com
MACs hmac-sha2-512-etm@openssh.com,hmac-sha2-256-etm@openssh.com
KexAlgorithms curve25519-sha256,curve25519-sha256@libssh.org
HostKeyAlgorithms ssh-ed25519,rsa-sha2-512,rsa-sha2-256
```

### 1.4 Idle Timeout

```bash
# /etc/ssh/sshd_config
ClientAliveInterval 300
ClientAliveCountMax 2
```

This disconnects idle sessions after 10 minutes (300s x 2).

### 1.5 Additional Restrictions

```bash
# /etc/ssh/sshd_config
MaxAuthTries 3
MaxSessions 3
AllowAgentForwarding no
X11Forwarding no
```

### Verification

```bash
sshd -T | grep -E 'permitrootlogin|passwordauthentication|pubkeyauthentication'
sshd -T | grep -E 'ciphers|macs|kexalgorithms'
sshd -T | grep -E 'clientaliveinterval|clientalivecountmax'
```

### Rollback

```bash
sudo cp /etc/ssh/sshd_config.bak /etc/ssh/sshd_config
sudo systemctl restart sshd
```

Always create a backup before making changes:
```bash
sudo cp /etc/ssh/sshd_config /etc/ssh/sshd_config.bak
```

---

## 2. Firewall Setup (UFW)

### 2.1 Default Deny Policy

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
```

### 2.2 Allow SSH (Critical — Do This First)

```bash
sudo ufw allow ssh        # port 22
# or for a custom port:
sudo ufw allow 2222/tcp
```

### 2.3 Rate Limiting SSH

```bash
sudo ufw limit ssh
```

Limits connection attempts to 6 per 30 seconds per IP.

### 2.4 Enable the Firewall

**Only after allowing SSH:**

```bash
sudo ufw enable
```

### 2.5 Additional Service Rules

```bash
# Allow HTTP/HTTPS if running a web server
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Allow specific IP only
sudo ufw allow from 192.168.1.0/24 to any port 22
```

### Verification

```bash
sudo ufw status verbose
sudo ufw status numbered
```

### Rollback

```bash
sudo ufw disable
# or remove specific rules:
sudo ufw delete <rule_number>
# full reset:
sudo ufw reset
```

---

## 3. Fail2ban Integration

### 3.1 Installation

```bash
sudo apt install fail2ban
sudo systemctl enable fail2ban
```

### 3.2 SSH Jail Configuration

Create `/etc/fail2ban/jail.local`:

```ini
[sshd]
enabled = true
port = ssh
filter = sshd
logpath = /var/log/auth.log
maxretry = 3
bantime = 3600
findtime = 600
```

### 3.3 Start and Verify

```bash
sudo systemctl restart fail2ban
sudo fail2ban-client status
sudo fail2ban-client status sshd
```

### Verification

```bash
sudo fail2ban-client status sshd
# Shows banned IPs, total bans, current failures
```

### Rollback

```bash
# Unban a specific IP
sudo fail2ban-client set sshd unbanip <IP>
# Disable jail
sudo fail2ban-client stop
```

---

## 4. SSH Tunnel Hardening

### 4.1 Bind to Localhost Only

When creating tunnels, always bind to 127.0.0.1:

```bash
ssh -L 127.0.0.1:8080:remote:80 user@server
```

In sshd_config:
```bash
GatewayPorts no
AllowTcpForwarding local
```

### 4.2 Dedicated Tunnel Keys

Generate a key pair used only for tunneling:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/tunnel_key -C "tunnel-only"
```

### 4.3 Forced Commands

Restrict the tunnel key to only allow tunneling in `authorized_keys`:

```
restrict,port-forwarding,command="/bin/false" ssh-ed25519 AAAA... tunnel-only
```

This prevents shell access while allowing port forwarding.

### 4.4 Per-Host Configuration

In `~/.ssh/config`:

```
Host tunnel-server
    HostName 10.0.0.5
    User tunnel
    IdentityFile ~/.ssh/tunnel_key
    LocalForward 127.0.0.1:8080 localhost:80
    ExitOnForwardFailure yes
    ServerAliveInterval 60
```

### Verification

```bash
# Check active tunnels
ss -tlnp | grep ssh
# Verify forced command
ssh -T tunnel-server   # should fail with no shell
```

### Rollback

```bash
# Remove the forced command line from authorized_keys
# Revoke the tunnel key
ssh-keygen -R tunnel-server
```

---

## 5. Quick Reference: Verification Commands

| Check | Command |
|-------|---------|
| SSH config | `sshd -T` |
| Listening ports | `ss -tlnp` |
| Firewall status | `ufw status verbose` |
| Fail2ban status | `fail2ban-client status` |
| SSH auth log | `journalctl -u ssh -n 50` |
| Active connections | `ss -tunp` |
| Authorized keys | `cat ~/.ssh/authorized_keys` |

---

## 6. OpenClaw Integration

The `ssh_hardening` skill automates these steps with safety checks:

- **Audit**: `"ssh security audit"` — reads current config, shows recommendations
- **Harden**: `"harden ssh config"` — creates approval requests for each change
- **Apply**: `"ssh hardening apply <id>"` — executes approved changes
- **Verify**: Agent 2 automatically audits after changes are applied

All write operations require human approval through the Overseer system.
