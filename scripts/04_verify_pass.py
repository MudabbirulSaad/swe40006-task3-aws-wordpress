"""Verify the original local WordPress stage before changing its database."""
from task3lib import *
import requests
s=state()
commands=f'''set -eu
date -Is
cloud-init status --long || true
cat /var/lib/task3/bootstrap.done
echo '--- Installed versions and service state ---'
php --version
mysql --version
systemctl is-enabled httpd php-fpm mariadb
systemctl is-active httpd php-fpm mariadb
cd /var/www/html
/usr/local/bin/wp core is-installed --allow-root
/usr/local/bin/wp core version --allow-root
/usr/local/bin/wp db query 'SELECT ID,post_title,post_status FROM wp_posts WHERE post_type="post"; SELECT COUNT(*) AS post_rows FROM wp_posts;' --allow-root
echo '--- SSH host public key for independent verification ---'
cat /etc/ssh/ssh_host_ed25519_key.pub
echo '--- Published baseline response ---'
curl -fsS -o /dev/null -w 'HTTP_RESULT=%{{http_code}}\\n' http://{s['PassPublicIp']}/
aws s3 cp /var/log/task3-bootstrap.log s3://{s['bucket']}/evidence/E03_bootstrap.log --region {REGION}
if test -f /var/log/task3-recovery.log; then aws s3 cp /var/log/task3-recovery.log s3://{s['bucket']}/evidence/E03_recovery.log --region {REGION}; fi
echo PASS_LOCAL_APPLICATION_VERIFIED
'''
run_ssm(s["PassInstance"],commands,"E03_E04_pass_verification",timeout=900)
client("s3").download_file(s["bucket"],"evidence/E03_bootstrap.log",str(LOGS/"E03_full_bootstrap.log"))
response=requests.get(s["pass_url"]+"/?task3_check="+str(int(time.time())),timeout=30)
record={"at_utc":now(),"requested_url":response.url,"status":response.status_code,
        "baseline_title_present":"Task 3 baseline record" in response.text,
        "headers":dict(response.headers),"body_file":"E04_public_baseline.html"}
save("E04_public_baseline.html",response.text)
save("E04_public_baseline.json",record)
if response.status_code!=200 or not record["baseline_title_present"]:raise RuntimeError(record)
save("E02_initial_security_groups.json",client("ec2").describe_security_groups(GroupIds=[s["PassSG"]]))
save("E03_initial_instance.json",client("ec2").describe_instances(InstanceIds=[s["PassInstance"]]))
update(pass_verified_at=record["at_utc"])
event("pass_stage_verified",**record)
