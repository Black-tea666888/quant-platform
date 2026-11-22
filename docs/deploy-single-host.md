# Single-host deployment (invite-only)

This guide follows the launch decisions in the README: invite-only accounts, one Linux host,
HTTPS through a reverse proxy, and SQLite on a persistent disk. It is a starting point, not a
security audit. Read the "Still required" list in the README before exposing the app to anyone.

Replace `example.com` and the paths below with your own values.

## 1. Prepare the host

```bash
sudo useradd --system --create-home --shell /usr/sbin/nologin quant
sudo mkdir -p /opt/quant-platform /var/lib/quant-platform/workspace
sudo chown -R quant:quant /var/lib/quant-platform
# Copy or clone the repo into /opt/quant-platform, then:
cd /opt/quant-platform
sudo -u quant python3 -m venv .venv
sudo -u quant .venv/bin/pip install -r requirements.txt -r requirements-ui.txt
```

## 2. Create the first admin (operator only)

```bash
sudo -u quant /opt/quant-platform/.venv/bin/python -m quant_platform.accounts_cli \
  --db /var/lib/quant-platform/accounts.sqlite --workspace /var/lib/quant-platform/workspace \
  create --email you@example.com --role admin
```

Further accounts are created the same way. There is no self-signup.

## 3. Run the app as a service

`/etc/systemd/system/quant-platform.service`:

```ini
[Unit]
Description=quant-platform (Streamlit)
After=network-online.target

[Service]
User=quant
WorkingDirectory=/opt/quant-platform
Environment=QP_AUTH_DB=/var/lib/quant-platform/accounts.sqlite
Environment=QP_WORKSPACE=/var/lib/quant-platform/workspace
ExecStart=/opt/quant-platform/.venv/bin/streamlit run app.py --server.address 127.0.0.1 --server.port 8501 --server.headless true --browser.gatherUsageStats false
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now quant-platform
journalctl -u quant-platform -n 50
```

Streamlit listens on `127.0.0.1` only. Do not open port 8501 to the internet.

## 4. HTTPS with a reverse proxy (Caddy example)

`/etc/caddy/Caddyfile`:

```
example.com {
    reverse_proxy 127.0.0.1:8501
}
```

Caddy obtains and renews the certificate automatically and proxies the WebSocket that Streamlit needs.

## 5. Firewall

Allow only 22 (SSH, ideally key-only), 80, and 443. Block everything else.

## 6. Backups

Nightly, back up the accounts database and the per-user workspace. Use SQLite's online backup so the copy is consistent:

```bash
sqlite3 /var/lib/quant-platform/accounts.sqlite ".backup '/var/backups/quant/accounts-$(date +%F).sqlite'"
tar -C /var/lib/quant-platform -czf /var/backups/quant/workspace-$(date +%F).tgz workspace
```

Keep backups off the host. Test a restore before you rely on them.

## 7. Operating checks

- Audit trail: `accounts_cli ... audit --limit 50`. Look for repeated `login_fail` or `login_locked`.
- Password reset: `accounts_cli ... reset-password --email you@example.com`.
- Updates: `git pull`, `pip install -r requirements.txt -r requirements-ui.txt`, `systemctl restart quant-platform`.

## Known gaps before this serves anyone else

- No rate limiting at the proxy. Add one (for example Caddy's rate-limit plugin) or a fail2ban rule.
- No email verification or web password reset. Resets are operator-only.
- Uploaded CSVs and generated reports are kept in the workspace. Decide a retention period.
- Not yet reviewed for security. Schedule a review before any wider use.
- Legal review is still required before public or paid use. See the README.
