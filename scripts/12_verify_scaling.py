from task3lib import *
import requests
s=state();elbv2=client('elbv2');asg=client('autoscaling');ec2=client('ec2')
for _ in range(120):
    group=asg.describe_auto_scaling_groups(AutoScalingGroupNames=[PREFIX+'-web-asg'])['AutoScalingGroups'][0]
    health=elbv2.describe_target_health(TargetGroupArn=s['TargetGroupArn'])
    healthy=[x['Target']['Id'] for x in health['TargetHealthDescriptions'] if x['TargetHealth']['State']=='healthy']
    if len(healthy)==2 and len(group['Instances'])==2:break
    time.sleep(5)
else:
    save('E13_unhealthy_targets.json',health);raise TimeoutError('Two healthy ALB targets')
ids=sorted(healthy);assert len({i['AvailabilityZone'] for i in group['Instances']})==2
save('E12_asg_configuration.json',group);save('E13_target_health.json',health)
save('E11_alb_configuration.json',elbv2.describe_load_balancers(LoadBalancerArns=[s['AlbArn']]))
save('E10_final_launch_template.json',ec2.describe_launch_template_versions(LaunchTemplateId=group['LaunchTemplate']['LaunchTemplateId'],Versions=[group['LaunchTemplate']['Version']]))
for iid in ids:
    commands='''set -eu
date -Is
hostname
cloud-init status --wait
cat /var/lib/task3/web-startup.done
cat /var/log/task3-web-startup.log
systemctl is-active httpd php-fpm amazon-ssm-agent
stat -c '%a %U:%G %n' /var/www/html/wp-config.php
cd /var/www/html
/usr/local/bin/wp post list --allow-root --fields=ID,post_title,post_status --format=table
/usr/local/bin/wp eval 'global $wpdb; echo json_encode($wpdb->get_results("SHOW SESSION STATUS LIKE \\"Ssl_cipher\\"")),PHP_EOL;' --allow-root
echo 'Master-secret access must fail (only parameter name is requested):'
if aws ssm get-parameter --name /swe40006/t3/migration/db-master --with-decryption --query Parameter.Name --output text --region ap-southeast-2; then echo 'ERROR: master parameter unexpectedly allowed'; exit 1; else echo 'EXPECTED_MASTER_PARAMETER_DENIED'; fi
echo 'SSH ingress is verified separately from every attached SG.'
'''
    run_ssm(iid,commands,'E13_E16_backend_'+iid,600)
rows=[]
for n in range(16):
    r=requests.get(s['final_url']+'/?proof='+str(time.time_ns()),timeout=20,headers={'Connection':'close','Cache-Control':'no-cache'})
    row={'at_utc':now(),'status':r.status_code,'node':r.headers.get('X-Task3-Node'),'baseline_present':'Task 3 baseline record' in r.text,'rds_post_present':'RDS migration verified' in r.text,'url':r.url}
    rows.append(row)
    assert r.status_code==200 and row['baseline_present'] and row['rds_post_present'],row
save('E13_public_alb_requests.json',rows)
assert set(x['node'] for x in rows)==set(ids),rows
instances=ec2.describe_instances(InstanceIds=ids)
sgids=sorted({g['GroupId'] for res in instances['Reservations'] for i in res['Instances'] for g in i['SecurityGroups']})
groups=ec2.describe_security_groups(GroupIds=sgids)
for g in groups['SecurityGroups']:
    for rule in g['IpPermissions']:
        assert rule['IpProtocol']!='-1' and not(rule['IpProtocol']=='tcp' and rule['FromPort']<=22<=rule['ToPort']),rule
save('E17_all_backend_security_groups.json',groups);save('E16_backend_instances.json',instances)
update(final_instances=ids,scaling_verified_at=now(),AsgName=PREFIX+'-web-asg',LaunchTemplateId=group['LaunchTemplate']['LaunchTemplateId'])
event('distinction_verified',instances=ids,url=s['final_url'],requests=len(rows),distinct_nodes=sorted(set(x['node'] for x in rows)),ssh_ingress=False)
