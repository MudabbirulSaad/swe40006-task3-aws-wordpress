"""Resume after the successful import; do not reimport or replace new RDS writes."""
from task3lib import *
import requests
s=state()
original=(IMPL/'scripts/migrate-rds.sh').read_text().replace('__DB_HOST__',s['DatabaseEndpoint']).replace('__BUCKET__',s['bucket'])
tail=original[original.index('systemctl disable --now mariadb'):]
header=f'''#!/bin/bash
set -Eeuo pipefail
umask 077
exec > >(tee -a /var/log/task3-migration.log) 2>&1
export AWS_DEFAULT_REGION={REGION}
P=/root/task3-private
BUCKET='{s['bucket']}'
cd /var/www/html
echo "Resume migration after WP-CLI db query preflight failed; import already verified. $(date -Is)"
/usr/local/bin/wp eval 'global $wpdb; echo json_encode($wpdb->get_results("SHOW SESSION STATUS LIKE \\"Ssl_cipher\\"")),PHP_EOL;' --allow-root
'''
run_ssm(s['PassInstance'],header+tail,'E07_migration_resume',600)
r=requests.get(s['pass_url']+'/?check='+str(int(time.time())),timeout=30)
record={'at_utc':now(),'url':r.url,'status':r.status_code,'baseline_present':'Task 3 baseline record' in r.text,'new_rds_post_present':'RDS migration verified' in r.text}
save('E07_rds_public_test.json',record);save('E07_rds_public_test.html',r.text)
assert r.status_code==200 and record['baseline_present'] and record['new_rds_post_present'],record
update(migration_verified_at=now());event('rds_migration_verified',**record)
