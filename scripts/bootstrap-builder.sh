#!/bin/bash
set -Eeuo pipefail
exec > >(tee -a /var/log/task3-image-build.log) 2>&1
trap 'echo "IMAGE_BUILD_ERROR line=$LINENO exit=$? $(date -Is)"' ERR
echo "Clean AL2023 image build $(date -Is)"
dnf install -y httpd php php-fpm php-mysqlnd php-gd php-xml php-mbstring jq
systemctl enable httpd php-fpm amazon-ssm-agent
curl -fsSL --retry 3 https://raw.githubusercontent.com/wp-cli/builds/gh-pages/phar/wp-cli.phar -o /usr/local/bin/wp
chmod 755 /usr/local/bin/wp
install -d -m 700 /root/task3-build
aws s3 cp 's3://__BUCKET__/releases/wordpress-release.tar.gz' /root/task3-build/wp-files.tar.gz --region ap-southeast-2 --no-progress
aws s3 cp 's3://__BUCKET__/releases/wordpress-release.tar.gz.sha256' /root/task3-build/wp-files.tar.gz.sha256 --region ap-southeast-2 --no-progress
cd /root/task3-build
sha256sum -c wp-files.tar.gz.sha256
tar -xzf wp-files.tar.gz -C /var/www/html
test ! -e /var/www/html/wp-config.php
curl -fsSL --retry 3 https://truststore.pki.rds.amazonaws.com/ap-southeast-2/ap-southeast-2-bundle.pem -o /etc/pki/ca-trust/source/anchors/task3-rds.pem
update-ca-trust
chown -R apache:apache /var/www/html
find /var/www/html -type d -exec chmod 755 {} \;
find /var/www/html -type f -exec chmod 644 {} \;
php --version
httpd -v
/usr/local/bin/wp core version --path=/var/www/html --allow-root
echo 'Private runtime wp-config not baked into image; local MariaDB not installed.'
install -d /var/lib/task3
date -Is > /var/lib/task3/image-build.done
echo "TASK3_IMAGE_BUILD_COMPLETE $(date -Is)"
