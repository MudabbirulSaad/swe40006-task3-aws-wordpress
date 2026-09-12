"""Remove the retired migration server's access after final backend verification."""
from task3lib import *
s=state();assert s.get('scaling_verified_at') and s.get('replacement_verified_at')
path=IMPL/'infrastructure'/f'{PREFIX}-base.json';t=json.loads(path.read_text())
save('E17_before_retiring_pass_access.json',t)
t['Resources']['PassSG']['Properties']['SecurityGroupIngress']=[]
t['Resources']['DbSG']['Properties']['SecurityGroupIngress']=[{'IpProtocol':'tcp','FromPort':3306,'ToPort':3306,'SourceSecurityGroupId':{'Ref':'WebSG'}}]
# A stopped EC2 instance has no PublicIp attribute. Retire that live output;
# the original address remains in the immutable Pass evidence.
t['Outputs'].pop('PassPublicIp',None)
for role,title in [('pass','PassRole'),('web','WebRole')]:
    t['Resources'][title]['Properties']['Policies'][0]['PolicyDocument']=json.loads((IMPL/'infrastructure'/f'{role}-runtime-policy.json').read_text())
try:client('cloudformation').update_stack(StackName=PREFIX+'-base',TemplateBody=json.dumps(t),Capabilities=['CAPABILITY_NAMED_IAM'])
except client('cloudformation').exceptions.ClientError as exc:
    if 'No updates are to be performed' not in str(exc):raise
path.write_text(json.dumps(t,indent=2));wait_stack(PREFIX+'-base')
save('E17_final_all_project_security_groups.json',client('ec2').describe_security_groups(GroupIds=[s[k] for k in ['PassSG','WebSG','AlbSG','DbSG']]))
sessions=[]
for iid in s['final_instances']:
    sessions.extend(client('ssm').describe_sessions(State='History',Filters=[{'key':'Target','value':iid}])['Sessions'])
save('E18_browser_session_history.json',sessions)
assert all(any(x['Target']==iid and x['Status']=='Terminated' for x in sessions) for iid in s['final_instances'])
update(ssm_sessions_verified_at=now(),retired_pass_access_removed_at=now());event('final_management_verified',instances=s['final_instances'],retired_pass_ingress='none',database_sources='final WebSG only',ssm_console_actor='existing root console session; operating-system user ssm-user')
