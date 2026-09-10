from task3lib import *
import base64
s=state();ec2=client('ec2')
assert s.get('image_verified_at') and s.get('AlbDns')
if not s.get('canonical_url_configured_at'):
    commands=f'''set -eu
cd /var/www/html
/usr/local/bin/wp option update home {s['final_url']} --allow-root
/usr/local/bin/wp option update siteurl {s['final_url']} --allow-root
/usr/local/bin/wp config set DISALLOW_FILE_MODS true --raw --allow-root
chown root:apache wp-config.php; chmod 640 wp-config.php
aws ssm put-parameter --name /swe40006/t3/runtime/wp-config --type SecureString --overwrite --value file:///var/www/html/wp-config.php --region {REGION}
echo 'Canonical URL set; final file edits frozen; runtime config published privately.'
'''
    run_ssm(s['PassInstance'],commands,'E10_canonical_runtime_configuration',180)
    s=update(canonical_url_configured_at=now())
# The two final 2-vCPU nodes need the five-vCPU quota. Preserve old disks, but stop both old instances.
ec2.stop_instances(InstanceIds=[s['PassInstance'],s['BuilderInstance']])
event('stop_pass_and_builder_for_final_capacity',instances=[s['PassInstance'],s['BuilderInstance']])
for _ in range(60):
    r=ec2.describe_instances(InstanceIds=[s['PassInstance'],s['BuilderInstance']])
    if all(i['State']['Name']=='stopped' for res in r['Reservations'] for i in res['Instances']):break
    time.sleep(5)
else:raise TimeoutError('Waiting for prior instances to stop')
save('E10_pre_asg_stopped_instances.json',r)
script=(IMPL/'scripts/bootstrap-web.sh').read_text()
lt={'LaunchTemplateName':PREFIX+'-web-template','VersionDescription':'WordPress 7.1 clean AMI; SSM runtime config; no SSH','LaunchTemplateData':{'ImageId':s['FinalAmi'],'InstanceType':'t3.micro','SecurityGroupIds':[s['WebSG']],'IamInstanceProfile':{'Name':s['WebRoleProfile']},'MetadataOptions':{'HttpTokens':'required','HttpEndpoint':'enabled'},'CreditSpecification':{'CpuCredits':'standard'},'BlockDeviceMappings':[{'DeviceName':'/dev/xvda','Ebs':{'VolumeSize':12,'VolumeType':'gp3','Encrypted':True,'DeleteOnTermination':True}}],'UserData':base64.b64encode(script.encode()).decode(),'TagSpecifications':[{'ResourceType':'instance','Tags':[{'Key':'Project','Value':PREFIX},{'Key':'Name','Value':PREFIX+'-asg-web'}]}]}}
lt['LaunchTemplateData']['Monitoring']={'Enabled':True}
R={'WebTemplate':{'Type':'AWS::EC2::LaunchTemplate','Properties':lt},'WebGroup':{'Type':'AWS::AutoScaling::AutoScalingGroup','Properties':{'AutoScalingGroupName':PREFIX+'-web-asg','MinSize':'2','DesiredCapacity':'2','MaxSize':'4','VPCZoneIdentifier':[s['PublicA'],s['PublicB']],'HealthCheckType':'ELB','HealthCheckGracePeriod':300,'DefaultInstanceWarmup':120,'TargetGroupARNs':[s['TargetGroupArn']],'LaunchTemplate':{'LaunchTemplateId':{'Ref':'WebTemplate'},'Version':{'Fn::GetAtt':['WebTemplate','LatestVersionNumber']}},'Tags':[{'Key':'Project','Value':PREFIX,'PropagateAtLaunch':True}]}}}
t={'AWSTemplateFormatVersion':'2010-09-09','Description':'Task 3 fixed 2-node ASG across two AZs; runtime secrets outside AMI and user data','Resources':R,'Outputs':{'LaunchTemplateId':{'Value':{'Ref':'WebTemplate'}},'AsgName':{'Value':{'Ref':'WebGroup'}}}}
deploy(PREFIX+'-scaling',t);out=wait_stack(PREFIX+'-scaling');update(**out);event('asg_created',**out)
