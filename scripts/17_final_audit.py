"""Read-only infrastructure, evidence and secret-exclusion checks."""
from task3lib import *
import ast,base64,re,hashlib
import requests
s=state();ec2=client('ec2');cf=client('cloudformation')
for path in (IMPL/'scripts').glob('*.py'):ast.parse(path.read_text(encoding='utf-8'),filename=str(path))
shells=list((IMPL/'scripts').glob('*.sh'))
commands=['set -eu','install -d -m 700 /tmp/task3-syntax-audit']
for path in shells:
    encoded=base64.b64encode(path.read_bytes()).decode()
    commands.extend([f"printf '%s' '{encoded}' | base64 -d > /tmp/task3-syntax-audit/{path.name}",f'bash -n /tmp/task3-syntax-audit/{path.name}',f"echo 'SYNTAX_OK {path.name}'"])
run_ssm(s['final_instances'][0],'\n'.join(commands),'E22_shell_syntax_audit',180,print_output=False)
templates=[]
for path in (IMPL/'infrastructure').glob(f'{PREFIX}-*.json'):
    cf.validate_template(TemplateBody=path.read_text());templates.append(path.name)
stack_status={name:cf.describe_stacks(StackName=PREFIX+'-'+name)['Stacks'][0]['StackStatus'] for name in ['base','database','loadbalancer','scaling']}
assert all(x in ['CREATE_COMPLETE','UPDATE_COMPLETE'] for x in stack_status.values()),stack_status
asg=client('autoscaling').describe_auto_scaling_groups(AutoScalingGroupNames=[s['AsgName']])['AutoScalingGroups'][0]
assert (asg['MinSize'],asg['DesiredCapacity'],asg['MaxSize'])==(2,2,4)
assert set(x['InstanceId'] for x in asg['Instances'])==set(s['final_instances'])
health=client('elbv2').describe_target_health(TargetGroupArn=s['TargetGroupArn'])
assert sorted(x['Target']['Id'] for x in health['TargetHealthDescriptions'] if x['TargetHealth']['State']=='healthy')==s['final_instances']
instances=ec2.describe_instances(InstanceIds=s['final_instances']+[s['PassInstance'],s['BuilderInstance']])
for res in instances['Reservations']:
    for i in res['Instances']:
        assert i['State']['Name']==('running' if i['InstanceId'] in s['final_instances'] else 'stopped')
credits=ec2.describe_instance_credit_specifications(InstanceIds=s['final_instances'])
assert all(i['CpuCredits']=='standard' for i in credits['InstanceCreditSpecifications']),credits
db=client('rds').describe_db_instances(DBInstanceIdentifier=s['DatabaseId'])['DBInstances'][0]
assert db['DBInstanceStatus']=='available' and not db['PubliclyAccessible'] and db['StorageEncrypted']
sgs=ec2.describe_security_groups(GroupIds=[s[x] for x in ['PassSG','WebSG','DbSG','AlbSG']])
for group in sgs['SecurityGroups']:
    for rule in group['IpPermissions']:
        assert rule['IpProtocol']!='-1' and not(rule['IpProtocol']=='tcp' and rule['FromPort']<=22<=rule['ToPort']),rule
dbsg=next(x for x in sgs['SecurityGroups'] if x['GroupId']==s['DbSG'])
assert {u['GroupId'] for r in dbsg['IpPermissions'] for u in r.get('UserIdGroupPairs',[])}=={s['WebSG']}
http=[]
for n in range(8):
    r=requests.get(s['final_url']+'/?final_audit='+str(time.time_ns()),timeout=15,headers={'Connection':'close'})
    row={'at_utc':now(),'status':r.status_code,'node':r.headers.get('X-Task3-Node'),'baseline':'Task 3 baseline record' in r.text,'rds_post':'RDS migration verified' in r.text};http.append(row)
    assert row['status']==200 and row['baseline'] and row['rds_post'],row
subs=client('sns').list_subscriptions_by_topic(TopicArn=s['SnsTopic'])
alarm=client('cloudwatch').describe_alarms(AlarmNames=[s['AlarmName']])['MetricAlarms'][0]
assert alarm['StateValue']=='OK' and alarm['ActionsEnabled']
save('E22_final_resource_inventory.json',{'at_utc':now(),'stacks':stack_status,'asg':asg,'targets':health,'instances':instances,'credits':credits,'database':db,'security_groups':sgs,'http':http,'alarm':alarm,'subscriptions':subs})
# Scan only evidence/source text; no values are emitted. Include real runtime config secrets.
credentials=json.loads((PRIVATE/'task3-operator-credentials.json').read_text())
secrets_to_exclude=[credentials['aws_secret_access_key'],credentials['aws_access_key_id'],(PRIVATE/'database-master-password.txt').read_text().strip(),(PRIVATE/'wordpress-admin-password.txt').read_text().strip()]
config=client('ssm').get_parameter(Name='/swe40006/t3/runtime/wp-config',WithDecryption=True)['Parameter']['Value']
for key,value in re.findall(r"define\(\s*'([^']+)'\s*,\s*'([^']*)'\s*\)",config):
    if key=='DB_PASSWORD' or key.endswith('_KEY') or key.endswith('_SALT'):secrets_to_exclude.append(value)
hits=[];count=0
for folder in [IMPL,ROOT/'04_evidence']:
    for path in folder.rglob('*'):
        if path.suffix.lower() not in ['.json','.jsonl','.log','.txt','.md','.py','.sh']:continue
        text=path.read_text(encoding='utf-8',errors='replace');count+=1
        # Access-key IDs can be retained as non-secret metadata in private audit logs,
        # but are excluded along with secrets from the shareable implementation.
        values=secrets_to_exclude if IMPL in path.parents else [x for x in secrets_to_exclude if x!=credentials['aws_access_key_id']]
        if any(value and len(value)>=16 and (value in text or json.dumps(value)[1:-1] in text) for value in values):hits.append(str(path.relative_to(ROOT)))
assert not hits,{'secret_scan_failed_paths':hits}
result={'at_utc':now(),'python_syntax':'passed','bash_syntax_files':len(shells),'cloudformation_templates_validated':templates,'resource_checks':'passed','public_http_samples':len(http),'secret_exclusion_text_files_checked':count,'secret_values_found':0,'sns_confirmed':any(x['SubscriptionArn']!='PendingConfirmation' for x in subs['Subscriptions']),'email_receipt_verified':False,'report':'deferred'}
save('E22_final_audit.json',result);update(final_audit_at=now());event('final_audit',**result)
