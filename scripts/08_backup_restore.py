from task3lib import *
s=state()
assert s.get('migration_verified_at')
assert not s.get('restore_verified_at')
commands=(IMPL/'scripts/backup-restore.sh').read_text().replace('__BUCKET__',s['bucket'])
run_ssm(s['PassInstance'],commands,'E08_E09_backup_restore',900)
s3=client('s3')
save('E08_s3_configuration.json',{'at_utc':now(),'public_access':s3.get_public_access_block(Bucket=s['bucket']), 'encryption':s3.get_bucket_encryption(Bucket=s['bucket']),'versioning':s3.get_bucket_versioning(Bucket=s['bucket']), 'objects':s3.list_object_versions(Bucket=s['bucket'])})
update(restore_verified_at=now());event('s3_restore_verified',scope='Same EC2; fresh directory; hash and file-tree match; independent loopback HTTP app and fixture; runtime secret and RDS reused')
