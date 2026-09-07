"""Narrow runtime permissions and initiate the authorised alert subscription."""
from task3lib import *
s=state()
iam=client('iam')
for role,write in [('pass',True),('web',False)]:
    statements=[{'Effect':'Allow','Action':['s3:GetObject']+(['s3:PutObject'] if write else []),'Resource':[f"arn:aws:s3:::{s['bucket']}/{p}/*" for p in (['backups','releases','evidence'] if write else ['releases'])]},
        {'Effect':'Allow','Action':'ssm:GetParameter','Resource':[f"arn:aws:ssm:{REGION}:{s['account']}:parameter/swe40006/t3/{p}" for p in (['runtime/wp-config','migration/db-master'] if write else ['runtime/wp-config'])]}]
    if write:statements.append({'Effect':'Allow','Action':'ssm:PutParameter','Resource':f"arn:aws:ssm:{REGION}:{s['account']}:parameter/swe40006/t3/runtime/wp-config"})
    # The AWS managed SSM core policy also permits GetParameter on '*'.
    # Explicitly deny other parameter paths so the narrow Allow is effective.
    statements.append({'Effect':'Deny','Action':['ssm:GetParameter','ssm:GetParameters','ssm:GetParametersByPath'],'NotResource':[f"arn:aws:ssm:{REGION}:{s['account']}:parameter/swe40006/t3/{p}" for p in (['runtime/wp-config','migration/db-master'] if write else ['runtime/wp-config'])]})
    policy={'Version':'2012-10-17','Statement':statements}
    iam.put_role_policy(RoleName=f'{PREFIX}-{role}-role',PolicyName='TaskArtifactsAndConfiguration',PolicyDocument=json.dumps(policy))
    save(f'E16_{role}_role_policy.json',policy)
    (IMPL/'infrastructure'/f'{role}-runtime-policy.json').write_text(json.dumps(policy,indent=2))
    event('instance_role_policy_refined',role=role,master_secret_allowed=write)
sns=client('sns')
topic=sns.create_topic(Name=PREFIX+'-alerts',Tags=[{'Key':'Project','Value':PREFIX}])['TopicArn']
email_path=PRIVATE/'alert-email.txt'
if not email_path.exists():raise RuntimeError('Supply authorised email in .private/alert-email.txt')
email=email_path.read_text().strip()
subs=sns.list_subscriptions_by_topic(TopicArn=topic)['Subscriptions']
if not any(x['Endpoint']==email for x in subs):
    sns.subscribe(TopicArn=topic,Protocol='email',Endpoint=email,ReturnSubscriptionArn=True)
subs=sns.list_subscriptions_by_topic(TopicArn=topic)['Subscriptions']
save('E20_subscription_initial.json',{'at_utc':now(),'topic':topic,'subscriptions':subs})
update(SnsTopic=topic)
event('sns_subscription_requested',topic=topic,status=[x['SubscriptionArn'] for x in subs])
