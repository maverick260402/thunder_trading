#!/bin/bash
set -e

PROJECT_DIR="/home/thunder/algo_bot/thunder_trading"

echo "=== Step 1: Locking down .env permissions ==="
chmod 600 "$PROJECT_DIR/.env"
chown thunder:thunder "$PROJECT_DIR/.env"
echo "✅ .env secured"

echo ""
echo "=== Step 2: Installing Nginx site config ==="
cp "$PROJECT_DIR/nginx-thunder-trading.conf" /etc/nginx/sites-available/thunder-trading
ln -sf /etc/nginx/sites-available/thunder-trading /etc/nginx/sites-enabled/thunder-trading
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx
echo "✅ Nginx configured and reloaded"

echo ""
echo "=== Step 3: Installing systemd service ==="
cp "$PROJECT_DIR/thunder-trading.service" /etc/systemd/system/thunder-trading.service
systemctl daemon-reload
systemctl enable thunder-trading
systemctl start thunder-trading
echo "✅ systemd service enabled and started"

echo ""
echo "=== Step 4: Configuring UFW firewall ==="
ufw allow 2222/tcp comment 'SSH'
ufw allow 80/tcp comment 'HTTP'
ufw allow 443/tcp comment 'HTTPS'
ufw --force enable
echo "✅ Firewall configured"

echo ""
echo "=== Step 5: Setting up log rotation ==="
cat > /etc/logrotate.d/thunder-trading << 'EOF'
/home/thunder/algo_bot/thunder_trading/logs/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 thunder thunder
    sharedscripts
    postrotate
        systemctl reload thunder-trading > /dev/null 2>&1 || true
    endscript
}
EOF
echo "✅ Log rotation configured"

echo ""
echo "=== Final Status ==="
systemctl status thunder-trading --no-pager
echo ""
ufw status
echo ""
echo "🎉 Deployment complete! App is running at http://168.144.91.55"
