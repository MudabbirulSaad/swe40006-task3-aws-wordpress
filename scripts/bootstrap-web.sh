#!/bin/bash
set -Eeuo pipefail
umask 077
exec > >(tee -a /var/log/task3-web-startup.log) 2>&1
trap 'echo "WEB_STARTUP_ERROR line=$LINENO exit=$? $(date -Is)"' ERR
export AWS_DEFAULT_REGION=ap-southeast-2
echo "Final web startup $(date -Is)"
systemctl stop httpd
for attempt in $(seq 1 18); do
  if aws ssm get-parameter --name /swe40006/t3/runtime/wp-config --with-decryption --query Parameter.Value --output text > /var/www/html/wp-config.php.pending; then break; fi
  sleep 5
done
test -s /var/www/html/wp-config.php.pending
php -l /var/www/html/wp-config.php.pending
install -o root -g apache -m 640 /var/www/html/wp-config.php.pending /var/www/html/wp-config.php
rm /var/www/html/wp-config.php.pending
TOKEN=$(curl -fsS -X PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 60')
NODE=$(curl -fsS -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/instance-id)
printf '%s\n' "$NODE" > /var/www/html/node.txt
chmod 644 /var/www/html/node.txt
printf 'Header always set X-Task3-Node "%s"\n' "$NODE" > /etc/httpd/conf.d/task3-node.conf
cat > /var/www/html/health.php <<'PHP'
<?php
header('Content-Type: application/json');
header('Cache-Control: no-store');
echo json_encode(['status'=>'ok','node'=>trim(file_get_contents(__DIR__.'/node.txt'))]);
PHP
chmod 644 /var/www/html/health.php
systemctl enable --now php-fpm httpd amazon-ssm-agent
cd /var/www/html
/usr/local/bin/wp eval 'global $wpdb; if ($wpdb->get_var("SELECT 1") != 1) { exit(1); } echo "RDS_CONNECTION_OK",PHP_EOL; echo json_encode($wpdb->get_results("SHOW SESSION STATUS LIKE \"Ssl_cipher\"")),PHP_EOL;' --allow-root
curl -fsS http://127.0.0.1/health.php
systemctl is-active php-fpm httpd amazon-ssm-agent
date -Is > /var/lib/task3/web-startup.done
echo "TASK3_WEB_STARTUP_COMPLETE node=$NODE $(date -Is)"
