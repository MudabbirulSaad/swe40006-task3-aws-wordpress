#!/bin/bash
set -Eeuo pipefail
umask 077
exec > >(tee -a /var/log/task3-migration.log) 2>&1
trap 'echo "MIGRATION_ERROR line=$LINENO exit=$? at=$(date -Is)"' ERR
export AWS_DEFAULT_REGION=ap-southeast-2
DB_HOST='__DB_HOST__'
BUCKET='__BUCKET__'
P=/root/task3-private
cd /var/www/html
echo "Migration started $(date -Is); baseline already publicly verified; writes frozen."
systemctl stop httpd php-fpm
trap 'systemctl start php-fpm httpd' EXIT
mysql --batch --skip-column-names wordpress_db -e 'SELECT ID,post_title,post_content,post_status FROM wp_posts ORDER BY ID' > "$P/source-records.tsv"
mysql --batch --skip-column-names wordpress_db -e 'SHOW TABLES' > "$P/tables.txt"
while read -r table; do mysql --batch --skip-column-names wordpress_db -e "SELECT '$table',COUNT(*) FROM \`$table\`;"; done < "$P/tables.txt" > "$P/source-counts.tsv"
echo 'Source exact table counts:'; cat "$P/source-counts.tsv"
mysqldump --single-transaction --databases wordpress_db > "$P/wordpress-before.sql"
test -s "$P/wordpress-before.sql"
sha256sum "$P/wordpress-before.sql"
curl -fsSL --retry 3 https://truststore.pki.rds.amazonaws.com/ap-southeast-2/ap-southeast-2-bundle.pem -o /etc/pki/ca-trust/source/anchors/task3-rds.pem
update-ca-trust
MASTER=$(aws ssm get-parameter --name /swe40006/t3/migration/db-master --with-decryption --query Parameter.Value --output text)
printf '[client]\nuser=t3master\npassword=%s\nhost=%s\nssl-ca=/etc/pki/ca-trust/source/anchors/task3-rds.pem\nssl-verify-server-cert\n' "$MASTER" "$DB_HOST" > "$P/rds-master.cnf"
unset MASTER
mysql --defaults-extra-file="$P/rds-master.cnf" -e 'SELECT VERSION(); SHOW SESSION STATUS LIKE "Ssl_cipher";'
if mysql --defaults-extra-file="$P/rds-master.cnf" --batch --skip-column-names -e "SHOW DATABASES LIKE 'wordpress_db';" | grep -qx wordpress_db; then
  echo 'Target database already exists. Stop and inspect the migration checkpoint; do not overwrite existing RDS writes.'
  exit 1
fi
mysql --defaults-extra-file="$P/rds-master.cnf" < "$P/wordpress-before.sql"
DB_PASSWORD=$(cat "$P/local-db-password")
mysql --defaults-extra-file="$P/rds-master.cnf" <<SQL
CREATE USER 'wp_user'@'%' IDENTIFIED BY '${DB_PASSWORD}' REQUIRE SSL;
GRANT ALL PRIVILEGES ON wordpress_db.* TO 'wp_user'@'%';
SQL
unset DB_PASSWORD
while read -r table; do mysql --defaults-extra-file="$P/rds-master.cnf" --batch --skip-column-names wordpress_db -e "SELECT '$table',COUNT(*) FROM \`$table\`;"; done < "$P/tables.txt" > "$P/target-counts.tsv"
mysql --defaults-extra-file="$P/rds-master.cnf" --batch --skip-column-names wordpress_db -e 'SELECT ID,post_title,post_content,post_status FROM wp_posts ORDER BY ID' > "$P/target-records.tsv"
echo 'Target exact table counts:'; cat "$P/target-counts.tsv"
diff -u "$P/source-counts.tsv" "$P/target-counts.tsv"
diff -u "$P/source-records.tsv" "$P/target-records.tsv"
echo 'EXACT_COUNTS_AND_POST_RECORDS_MATCH'
cp wp-config.php "$P/wp-config-local.php"
/usr/local/bin/wp config set DB_HOST "$DB_HOST" --allow-root
/usr/local/bin/wp config set MYSQL_CLIENT_FLAGS MYSQLI_CLIENT_SSL --raw --allow-root
/usr/local/bin/wp eval 'global $wpdb; echo json_encode($wpdb->get_results("SHOW SESSION STATUS LIKE \"Ssl_cipher\"")),PHP_EOL;' --allow-root
/usr/local/bin/wp eval 'global $wpdb; echo json_encode($wpdb->get_results("SELECT ID,post_title,post_status FROM wp_posts WHERE post_type=\"post\"")),PHP_EOL;' --allow-root
systemctl disable --now mariadb
systemctl is-active mariadb || true
/usr/local/bin/wp post create --allow-root --post_status=publish --post_title='RDS migration verified' --post_content="Deployment test fixture written to RDS at $(date -u +%FT%TZ) after local MariaDB was stopped." --porcelain
/usr/local/bin/wp post list --allow-root --fields=ID,post_title,post_status --format=table
mysql --defaults-extra-file="$P/rds-master.cnf" wordpress_db -e 'SELECT ID,post_title,post_status FROM wp_posts WHERE post_type="post";'
chown root:apache wp-config.php; chmod 640 wp-config.php
aws ssm put-parameter --name /swe40006/t3/runtime/wp-config --type SecureString --overwrite --value file:///var/www/html/wp-config.php
aws s3 cp "$P/wordpress-before.sql" "s3://$BUCKET/backups/wordpress-before-rds.sql"
systemctl start php-fpm httpd
curl -fsS http://localhost/ | grep -o 'RDS migration verified' | head -1
echo "TASK3_RDS_MIGRATION_COMPLETE $(date -Is)"
