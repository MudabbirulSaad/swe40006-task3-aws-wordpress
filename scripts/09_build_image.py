from task3lib import *
s=state();ec2=client('ec2')
assert s.get('restore_verified_at')
if not s.get('BuilderInstance'):
    script=(IMPL/'scripts/bootstrap-builder.sh').read_text().replace('__BUCKET__',s['bucket'])
    r=ec2.run_instances(ImageId=s['ami'],InstanceType='t3.micro',MinCount=1,MaxCount=1,
        IamInstanceProfile={'Name':s['WebRoleProfile']},SubnetId=s['PublicA'],SecurityGroupIds=[s['WebSG']],
        MetadataOptions={'HttpTokens':'required'},CreditSpecification={'CpuCredits':'standard'},
        BlockDeviceMappings=[{'DeviceName':'/dev/xvda','Ebs':{'VolumeSize':12,'VolumeType':'gp3','Encrypted':True,'DeleteOnTermination':True}}],
        UserData=script,TagSpecifications=[{'ResourceType':'instance','Tags':[{'Key':'Name','Value':PREFIX+'-clean-image-builder'},{'Key':'Project','Value':PREFIX}]}])
    iid=r['Instances'][0]['InstanceId'];s=update(BuilderInstance=iid);save('E10_builder_created.json',r);event('clean_builder_created',instance=iid)
iid=s['BuilderInstance']
for _ in range(120):
    info=client('ssm').describe_instance_information(Filters=[{'Key':'InstanceIds','Values':[iid]}])['InstanceInformationList']
    if info and info[0]['PingStatus']=='Online':break
    time.sleep(5)
else:raise TimeoutError('Builder SSM registration')
run_ssm(iid,'date -Is\ncloud-init status --wait\ntest -f /var/lib/task3/image-build.done\ntest ! -f /var/www/html/wp-config.php\ncat /var/log/task3-image-build.log\n','E10_clean_image_build',900)
if not s.get('FinalAmi'):
    r=ec2.create_image(InstanceId=iid,Name=PREFIX+'-wordpress-7-1-'+datetime.datetime.now().strftime('%Y%m%d%H%M%S'),Description='WordPress 7.1 files and AL2023 PHP/Apache; runtime config supplied through SSM, no DB data',NoReboot=False,
        TagSpecifications=[{'ResourceType':'image','Tags':[{'Key':'Project','Value':PREFIX}]},{'ResourceType':'snapshot','Tags':[{'Key':'Project','Value':PREFIX}]}])
    s=update(FinalAmi=r['ImageId']);event('create_clean_ami',image=s['FinalAmi'],builder=iid)
for _ in range(180):
    r=ec2.describe_images(ImageIds=[s['FinalAmi']]);status=r['Images'][0]['State']
    if status=='available':break
    if status=='failed':raise RuntimeError(r)
    time.sleep(5)
else:raise TimeoutError('AMI available')
save('E10_clean_ami.json',r)
ec2.stop_instances(InstanceIds=[iid]);event('stop_builder_after_ami_available',instance=iid,image=s['FinalAmi'])
update(image_verified_at=now())
