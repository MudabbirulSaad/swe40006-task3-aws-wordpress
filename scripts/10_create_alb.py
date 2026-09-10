from task3lib import *
s=state()
assert s.get('restore_verified_at')
R={
 'Alb':{'Type':'AWS::ElasticLoadBalancingV2::LoadBalancer','Properties':{'Name':PREFIX+'-alb','Type':'application','Scheme':'internet-facing','IpAddressType':'ipv4','Subnets':[s['PublicA'],s['PublicB']],'SecurityGroups':[s['AlbSG']],'LoadBalancerAttributes':[{'Key':'idle_timeout.timeout_seconds','Value':'60'}],'Tags':[{'Key':'Project','Value':PREFIX}]}},
 'Targets':{'Type':'AWS::ElasticLoadBalancingV2::TargetGroup','Properties':{'Name':PREFIX+'-targets','VpcId':s['Vpc'],'Protocol':'HTTP','Port':80,'TargetType':'instance','HealthCheckEnabled':True,'HealthCheckPath':'/health.php','HealthCheckProtocol':'HTTP','HealthCheckIntervalSeconds':15,'HealthyThresholdCount':2,'UnhealthyThresholdCount':3,'Matcher':{'HttpCode':'200'},'TargetGroupAttributes':[{'Key':'deregistration_delay.timeout_seconds','Value':'30'},{'Key':'stickiness.enabled','Value':'false'}],'Tags':[{'Key':'Project','Value':PREFIX}]}},
 'Listener':{'Type':'AWS::ElasticLoadBalancingV2::Listener','Properties':{'LoadBalancerArn':{'Ref':'Alb'},'Port':80,'Protocol':'HTTP','DefaultActions':[{'Type':'forward','TargetGroupArn':{'Ref':'Targets'}}]}}
}
t={'AWSTemplateFormatVersion':'2010-09-09','Description':'Task 3 two-zone public HTTP ALB; backends use private SG access','Resources':R,'Outputs':{'AlbArn':{'Value':{'Ref':'Alb'}},'TargetGroupArn':{'Value':{'Ref':'Targets'}},'AlbDns':{'Value':{'Fn::GetAtt':['Alb','DNSName']}}}}
deploy(PREFIX+'-loadbalancer',t)
out=wait_stack(PREFIX+'-loadbalancer');update(**out,final_url='http://'+out['AlbDns']);event('alb_created',**out)
