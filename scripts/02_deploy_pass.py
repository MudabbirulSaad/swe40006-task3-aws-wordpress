"""Create the isolated task network and initial local-database WordPress instance."""
import base64
import json
import urllib.request
from task3lib import *

ec2=client("ec2")
account=client("sts").get_caller_identity()["Account"]
keyname=PREFIX+"-pass-key"
keypath=PRIVATE/(keyname+".pem")
if not keypath.exists():
    result=ec2.create_key_pair(KeyName=keyname,KeyType="rsa",KeyFormat="pem",
        TagSpecifications=[{"ResourceType":"key-pair","Tags":[{"Key":"Project","Value":PREFIX}]}])
    keypath.write_text(result.pop("KeyMaterial"))
    result.pop("ResponseMetadata",None)
    save("E02_key_pair.json",result)
    event("create_key_pair",key_name=keyname,private_key="Private local file; excluded from evidence")
ip=urllib.request.urlopen("https://checkip.amazonaws.com",timeout=15).read().decode().strip()
ami=client("ssm").get_parameter(Name="/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64")["Parameter"]["Value"]
azs=sorted(z["ZoneName"] for z in ec2.describe_availability_zones(Filters=[{"Name":"state","Values":["available"]}])["AvailabilityZones"])[:2]
bucket=f"{PREFIX}-{account}-artifacts"
R={}
def add(name,typ,props,**extra):R[name]={"Type":typ,"Properties":props,**extra}
def ref(name):return {"Ref":name}
def att(name,key):return {"Fn::GetAtt":[name,key]}
def tags(name):return [{"Key":"Name","Value":PREFIX+"-"+name},{"Key":"Project","Value":PREFIX}]
add("Vpc","AWS::EC2::VPC",{"CidrBlock":"10.43.0.0/16","EnableDnsSupport":True,"EnableDnsHostnames":True,"Tags":tags("vpc")})
add("InternetGateway","AWS::EC2::InternetGateway",{"Tags":tags("igw")})
add("GatewayAttachment","AWS::EC2::VPCGatewayAttachment",{"VpcId":ref("Vpc"),"InternetGatewayId":ref("InternetGateway")})
add("PublicRoutes","AWS::EC2::RouteTable",{"VpcId":ref("Vpc"),"Tags":tags("public-routes")})
add("InternetRoute","AWS::EC2::Route",{"RouteTableId":ref("PublicRoutes"),"DestinationCidrBlock":"0.0.0.0/0","GatewayId":ref("InternetGateway")},DependsOn="GatewayAttachment")
add("PrivateRoutes","AWS::EC2::RouteTable",{"VpcId":ref("Vpc"),"Tags":tags("private-routes")})
for name,cidr,az,public in [("PublicA","10.43.1.0/24",azs[0],True),("PublicB","10.43.2.0/24",azs[1],True),("PrivateA","10.43.11.0/24",azs[0],False),("PrivateB","10.43.12.0/24",azs[1],False)]:
    add(name,"AWS::EC2::Subnet",{"VpcId":ref("Vpc"),"CidrBlock":cidr,"AvailabilityZone":az,"MapPublicIpOnLaunch":public,"Tags":tags(name.lower())})
    add(name+"Routes","AWS::EC2::SubnetRouteTableAssociation",{"SubnetId":ref(name),"RouteTableId":ref("PublicRoutes" if public else "PrivateRoutes")})
add("PassSG","AWS::EC2::SecurityGroup",{"GroupDescription":"Pass web access and SSH only from the task operator IP","VpcId":ref("Vpc"),"Tags":tags("pass-sg"),"SecurityGroupIngress":[{"IpProtocol":"tcp","FromPort":p,"ToPort":p,"CidrIp":ip+"/32" if p==22 else "0.0.0.0/0"} for p in (22,80,443)]})
add("AlbSG","AWS::EC2::SecurityGroup",{"GroupDescription":"Public HTTP entry point","VpcId":ref("Vpc"),"Tags":tags("alb-sg"),"SecurityGroupIngress":[{"IpProtocol":"tcp","FromPort":80,"ToPort":80,"CidrIp":"0.0.0.0/0"}]})
add("WebSG","AWS::EC2::SecurityGroup",{"GroupDescription":"Backend HTTP from ALB only; no SSH","VpcId":ref("Vpc"),"Tags":tags("web-sg"),"SecurityGroupIngress":[{"IpProtocol":"tcp","FromPort":80,"ToPort":80,"SourceSecurityGroupId":ref("AlbSG")}]})
add("DbSG","AWS::EC2::SecurityGroup",{"GroupDescription":"Database from task application groups only","VpcId":ref("Vpc"),"Tags":tags("db-sg"),"SecurityGroupIngress":[{"IpProtocol":"tcp","FromPort":3306,"ToPort":3306,"SourceSecurityGroupId":ref(g)} for g in ("PassSG","WebSG")]})
add("Artifacts","AWS::S3::Bucket",{"BucketName":bucket,"PublicAccessBlockConfiguration":{"BlockPublicAcls":True,"BlockPublicPolicy":True,"IgnorePublicAcls":True,"RestrictPublicBuckets":True},"BucketEncryption":{"ServerSideEncryptionConfiguration":[{"ServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]},"VersioningConfiguration":{"Status":"Enabled"},"Tags":tags("artifacts")},DeletionPolicy="Retain",UpdateReplacePolicy="Retain")
trust={"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ec2.amazonaws.com"},"Action":"sts:AssumeRole"}]}
for role,write in [("PassRole",True),("WebRole",False)]:
    statements=[{'Effect':'Allow','Action':['s3:GetObject']+(['s3:PutObject'] if write else []),'Resource':[f'arn:aws:s3:::{bucket}/{p}/*' for p in (['backups','releases','evidence'] if write else ['releases'])]},
        {'Effect':'Allow','Action':'ssm:GetParameter','Resource':[f'arn:aws:ssm:{REGION}:{account}:parameter/swe40006/t3/{p}' for p in (['runtime/wp-config','migration/db-master'] if write else ['runtime/wp-config'])]},
        {'Effect':'Deny','Action':['ssm:GetParameter','ssm:GetParameters','ssm:GetParametersByPath'],'NotResource':[f'arn:aws:ssm:{REGION}:{account}:parameter/swe40006/t3/{p}' for p in (['runtime/wp-config','migration/db-master'] if write else ['runtime/wp-config'])]}]
    if write:statements.append({'Effect':'Allow','Action':'ssm:PutParameter','Resource':f'arn:aws:ssm:{REGION}:{account}:parameter/swe40006/t3/runtime/wp-config'})
    add(role,"AWS::IAM::Role",{"RoleName":PREFIX+("-pass-role" if write else "-web-role"),"AssumeRolePolicyDocument":trust,"ManagedPolicyArns":["arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"],"Policies":[{"PolicyName":"TaskArtifactsAndConfiguration","PolicyDocument":{"Version":"2012-10-17","Statement":statements}}]})
    add(role+"Profile","AWS::IAM::InstanceProfile",{"InstanceProfileName":PREFIX+("-pass-profile" if write else "-web-profile"),"Roles":[ref(role)]})
userdata=(IMPL/"scripts/bootstrap-pass.sh").read_text()
add("PassLaunchTemplate","AWS::EC2::LaunchTemplate",{"LaunchTemplateName":PREFIX+"-pass-template","LaunchTemplateData":{"ImageId":ami,"InstanceType":"t3.micro","KeyName":keyname,"SecurityGroupIds":[ref("PassSG")],"IamInstanceProfile":{"Name":ref("PassRoleProfile")},"MetadataOptions":{"HttpTokens":"required","HttpEndpoint":"enabled"},"CreditSpecification":{"CpuCredits":"standard"},"BlockDeviceMappings":[{"DeviceName":"/dev/xvda","Ebs":{"VolumeSize":12,"VolumeType":"gp3","Encrypted":True,"DeleteOnTermination":True}}],"UserData":base64.b64encode(userdata.encode()).decode()}})
add("PassInstance","AWS::EC2::Instance",{"LaunchTemplate":{"LaunchTemplateId":ref("PassLaunchTemplate"),"Version":att("PassLaunchTemplate","LatestVersionNumber")},"SubnetId":ref("PublicA"),"Tags":tags("pass")},DependsOn="InternetRoute")
outputs={name:{"Value":ref(name)} for name in ["Vpc","PublicA","PublicB","PrivateA","PrivateB","PassSG","AlbSG","WebSG","DbSG","PassInstance","WebRoleProfile","PassRoleProfile"]}
outputs.update({"PassPublicIp":{"Value":att("PassInstance","PublicIp")},"Bucket":{"Value":ref("Artifacts")}})
template={"AWSTemplateFormatVersion":"2010-09-09","Description":"Task 3 isolated network, private artifacts, roles and initial local WordPress","Resources":R,"Outputs":outputs}
update(account=account,ami=ami,azs=azs,key_name=keyname,bucket=bucket,ssh_source=ip+"/32",instance_type="t3.micro")
deploy(PREFIX+"-base",template)
outputs=wait_stack(PREFIX+"-base")
update(**outputs,pass_url="http://"+outputs["PassPublicIp"])
save("E03_base_outputs.json",outputs)
event("pass_infrastructure_created",outputs=outputs,bootstrap_status="Must be verified separately")
