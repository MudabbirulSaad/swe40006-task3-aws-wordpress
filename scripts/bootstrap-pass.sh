#!/bin/bash
set -Eeuo pipefail
umask 077
exec > >(tee -a /var/log/task3-bootstrap.log) 2>&1
trap 'echo "BOOTSTRAP_ERROR line=$LINENO exit=$? at=$(date -Is)"' ERR
run() { printf '\n[%s] RUN:' "$(date -Is)"; printf ' %q' "$@"; printf '\n'; "$@"; }
run cat /etc/os-release
run dnf install -y httpd php php-fpm php-mysqlnd php-gd php-xml php-mbstring mariadb105-server jq
run systemctl enable --now httpd php-fpm mariadb amazon-ssm-agent
run php --version
run mysql --version
run systemctl is-active httpd php-fpm mariadb amazon-ssm-agent
run curl -fsSL --retry 3 https://raw.githubusercontent.com/wp-cli/builds/gh-pages/phar/wp-cli.phar -o /usr/local/bin/wp
run chmod 755 /usr/local/bin/wp
run sha256sum /usr/local/bin/wp
run /usr/local/bin/wp --info
install -d -m 700 /root/task3-private
openssl rand -hex 24 > /root/task3-private/local-db-password
openssl rand -hex 24 > /root/task3-private/wp-admin-password
# Secret values are supplied privately to the database/configuration commands.
DB_PASSWORD=$(cat /root/task3-private/local-db-password)
mysql <<SQL
CREATE DATABASE wordpress_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'wp_user'@'localhost' IDENTIFIED BY '${DB_PASSWORD}';
GRANT ALL PRIVILEGES ON wordpress_db.* TO 'wp_user'@'localhost';
SQL
echo "Created application database and local application user; secret not logged."
cd /var/www/html
run php -d memory_limit=512M /usr/local/bin/wp core download --allow-root --version=7.1
/usr/local/bin/wp config create --allow-root --dbname=wordpress_db --dbuser=wp_user --dbpass="$DB_PASSWORD" --dbhost=localhost
unset DB_PASSWORD
TOKEN=$(curl -fsS -X PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 60')
PUBLIC_IP=$(curl -fsS -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/public-ipv4)
/usr/local/bin/wp core install --allow-root --url="http://$PUBLIC_IP" --title='Task 3 WordPress Deployment Lab' --admin_user=t3admin --admin_password="$(cat /root/task3-private/wp-admin-password)" --admin_email=admin@example.invalid --skip-email
run /usr/local/bin/wp post create --allow-root --post_status=publish --post_title='Task 3 baseline record' --post_content="Deployment test fixture created at $(date -u +%FT%TZ). This record will be checked before and after migration to RDS." --porcelain
run /usr/local/bin/wp core version --allow-root
run /usr/local/bin/wp db query 'SELECT ID,post_title,post_status FROM wp_posts WHERE post_type="post"; SELECT COUNT(*) AS post_rows FROM wp_posts;' --allow-root
run chown -R apache:apache /var/www/html
find /var/www/html -type d -exec chmod 755 {} \;
find /var/www/html -type f -exec chmod 644 {} \;
chown root:apache /var/www/html/wp-config.php
chmod 640 /var/www/html/wp-config.php
run curl -fsS -o /dev/null -w 'HTTP_RESULT=%{http_code}\n' "http://$PUBLIC_IP/"
mkdir -p /var/lib/task3
date -Is > /var/lib/task3/bootstrap.done
echo "TASK3_PASS_BOOTSTRAP_COMPLETE public_ip=$PUBLIC_IP at=$(date -Is)"
