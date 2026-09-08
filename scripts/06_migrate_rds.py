from task3lib import *
import requests
s=state()
assert s.get('pass_verified_at'), 'Verify Pass before migration'
assert not s.get('migration_verified_at'), 'Migration already verified; do not reimport'
commands=(IMPL/'scripts/migrate-rds.sh').read_text().replace('__DB_HOST__',s['DatabaseEndpoint']).replace('__BUCKET__',s['bucket'])
run_ssm(s['PassInstance'],commands,'E06_E07_rds_migration',timeout=900)
r=requests.get(s['pass_url']+'/?check='+str(int(time.time())),timeout=30)
record={'at_utc':now(),'url':r.url,'status':r.status_code,'baseline_present':'Task 3 baseline record' in r.text,'new_rds_post_present':'RDS migration verified' in r.text}
save('E07_rds_public_test.json',record); save('E07_rds_public_test.html',r.text)
assert r.status_code==200 and record['baseline_present'] and record['new_rds_post_present'],record
update(migration_verified_at=now()); event('rds_migration_verified',**record)
