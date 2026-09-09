#!/bin/bash
set -Eeuo pipefail
umask 077
exec > >(tee -a /var/log/task3-backup-restore.log) 2>&1
export AWS_DEFAULT_REGION=ap-southeast-2
P=/root/task3-private
BUCKET='__BUCKET__'
RESTORE=/root/task3-restore
test ! -e "$RESTORE"
echo "Manual S3 backup and isolated EC2 restore started $(date -Is)"
install -d -m 755 /var/www/html/wp-content/uploads
printf 'Task 3 file restore test fixture created %s\n' "$(date -u +%FT%TZ)" > /var/www/html/wp-content/uploads/task3-proof.txt
chmod 644 /var/www/html/wp-content/uploads/task3-proof.txt
tar --exclude='./wp-config.php' -czf "$P/wp-files.tar.gz" -C /var/www/html .
cd "$P"
sha256sum wp-files.tar.gz | tee wp-files.tar.gz.sha256
stat -c 'Archive bytes: %s' wp-files.tar.gz
if tar -tzf wp-files.tar.gz | grep -qx './wp-config.php'; then echo 'ERROR secret config in archive'; exit 1; fi
aws s3 cp wp-files.tar.gz "s3://$BUCKET/backups/wp-files.tar.gz"
aws s3 cp wp-files.tar.gz.sha256 "s3://$BUCKET/backups/wp-files.tar.gz.sha256"
mysqldump --defaults-extra-file="$P/rds-master.cnf" --single-transaction --databases wordpress_db > "$P/wordpress-rds-current.sql"
aws s3 cp wordpress-rds-current.sql "s3://$BUCKET/backups/wordpress-rds-current.sql"
install -d -m 700 "$RESTORE/download" "$RESTORE/html"
aws s3 cp "s3://$BUCKET/backups/wp-files.tar.gz" "$RESTORE/download/wp-files.tar.gz"
aws s3 cp "s3://$BUCKET/backups/wp-files.tar.gz.sha256" "$RESTORE/download/wp-files.tar.gz.sha256"
cd "$RESTORE/download"
sha256sum -c wp-files.tar.gz.sha256
tar -xzf wp-files.tar.gz -C "$RESTORE/html"
diff -qr --exclude=wp-config.php /var/www/html "$RESTORE/html"
echo 'RESTORED_FILE_TREE_MATCHES_SOURCE'
cp /var/www/html/wp-config.php "$RESTORE/html/wp-config.php"
cd "$RESTORE/html"
/usr/local/bin/wp config set WP_HOME http://127.0.0.1:8081 --allow-root
/usr/local/bin/wp config set WP_SITEURL http://127.0.0.1:8081 --allow-root
php -S 127.0.0.1:8081 -t "$RESTORE/html" > "$RESTORE/php-server.log" 2>&1 &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null || true' EXIT
for attempt in $(seq 1 10); do if curl -fsS http://127.0.0.1:8081/ -o "$RESTORE/restored-response.html"; then break; fi; sleep 1; done
grep -o 'Task 3 baseline record\|RDS migration verified' "$RESTORE/restored-response.html"
curl -fsS http://127.0.0.1:8081/wp-content/uploads/task3-proof.txt
sha256sum /var/www/html/wp-content/uploads/task3-proof.txt "$RESTORE/html/wp-content/uploads/task3-proof.txt"
kill "$SERVER_PID"; trap - EXIT
aws s3 cp "$P/wp-files.tar.gz" "s3://$BUCKET/releases/wordpress-release.tar.gz"
aws s3 cp "$P/wp-files.tar.gz.sha256" "s3://$BUCKET/releases/wordpress-release.tar.gz.sha256"
echo "TASK3_BACKUP_RESTORE_COMPLETE $(date -Is); same EC2 separate restore directory and loopback server; shared RDS/config dependencies stated."
