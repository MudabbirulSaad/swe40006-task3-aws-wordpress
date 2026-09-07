#!/bin/bash
set -Eeuo pipefail
umask 077
exec > >(tee -a /var/log/task3-recovery.log) 2>&1
trap 'echo "RECOVERY_ERROR line=$LINENO exit=$? at=$(date -Is)"' ERR
echo "Recovery started $(date -Is); original cloud-init failure retained."
cd /var/www/html
php -d memory_limit=512M /usr/local/bin/wp core download --allow-root --version=7.1 --force
/usr/local/bin/wp config create --allow-root --dbname=wordpress_db --dbuser=wp_user --dbpass="$(cat /root/task3-private/local-db-password)" --dbhost=localhost
TOKEN=$(curl -fsS -X PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 60')
PUBLIC_IP=$(curl -fsS -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/public-ipv4)
/usr/local/bin/wp core install --allow-root --url="http://$PUBLIC_IP" --title='Task 3 WordPress Deployment Lab' --admin_user=t3admin --admin_password="$(cat /root/task3-private/wp-admin-password)" --admin_email=admin@example.invalid --skip-email
/usr/local/bin/wp post create --allow-root --post_status=publish --post_title='Task 3 baseline record' --post_content="Deployment test fixture created at $(date -u +%FT%TZ). This record will be checked before and after migration to RDS." --porcelain
/usr/local/bin/wp core version --allow-root
/usr/local/bin/wp db query 'SELECT ID,post_title,post_status FROM wp_posts WHERE post_type="post"; SELECT COUNT(*) AS post_rows FROM wp_posts;' --allow-root
chown -R apache:apache /var/www/html
find /var/www/html -type d -exec chmod 755 {} \;
find /var/www/html -type f -exec chmod 644 {} \;
chown root:apache /var/www/html/wp-config.php
chmod 640 /var/www/html/wp-config.php
curl -fsS -o /dev/null -w 'HTTP_RESULT=%{http_code}\n' "http://$PUBLIC_IP/"
mkdir -p /var/lib/task3
date -Is > /var/lib/task3/bootstrap.done
echo "TASK3_PASS_RECOVERY_COMPLETE $(date -Is)"
