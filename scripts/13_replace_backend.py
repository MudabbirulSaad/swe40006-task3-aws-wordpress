"""Exercise planned ASG replacement while sampling public application responses."""
from task3lib import *
import requests
s=state();assert s.get('scaling_verified_at');assert not s.get('replacement_verified_at')
asg=client('autoscaling');elb=client('elbv2')
before=asg.describe_auto_scaling_groups(AutoScalingGroupNames=[s['AsgName']])['AutoScalingGroups'][0]
ids=sorted(x['InstanceId'] for x in before['Instances']);victim=ids[0]
save('E15_before_replacement.json',before)
r=asg.terminate_instance_in_auto_scaling_group(InstanceId=victim,ShouldDecrementDesiredCapacity=False)
save('E15_requested_replacement.json',r);event('planned_asg_replacement_requested',instance=victim,desired_capacity=2)
start=time.monotonic();rows=[];states=[];previous=None
for n in range(300):
    row={'at_utc':now()}
    try:
        response=requests.get(s['final_url']+'/?replacement='+str(time.time_ns()),timeout=10,headers={'Connection':'close'})
        row.update(status=response.status_code,node=response.headers.get('X-Task3-Node'),baseline_present='Task 3 baseline record' in response.text,rds_post_present='RDS migration verified' in response.text)
    except requests.RequestException as exc:row['error']=str(exc)
    rows.append(row)
    with (LOGS/'E15_live_requests.jsonl').open('a',encoding='utf-8') as stream:stream.write(json.dumps(row)+'\n')
    if n%3==0:
        group=asg.describe_auto_scaling_groups(AutoScalingGroupNames=[s['AsgName']])['AutoScalingGroups'][0]
        health=elb.describe_target_health(TargetGroupArn=s['TargetGroupArn'])
        live=sorted(x['InstanceId'] for x in group['Instances'])
        healthy=sorted(x['Target']['Id'] for x in health['TargetHealthDescriptions'] if x['TargetHealth']['State']=='healthy')
        state_row={'at_utc':now(),'instances':group['Instances'],'targets':health['TargetHealthDescriptions']};states.append(state_row)
        signature=str((live,healthy))
        if signature!=previous:event('replacement_progress',instances=live,healthy=healthy);previous=signature
        if len(live)==2 and healthy==live and victim not in live and any(x not in ids for x in live):break
    time.sleep(2)
else:raise TimeoutError('ASG replacement did not reach two healthy nodes')
save('E15_replacement_state_transitions.json',states)
save('E15_scaling_activities.json',asg.describe_scaling_activities(AutoScalingGroupName=s['AsgName']))
failures=[r for r in rows if r.get('status')!=200 or not r.get('baseline_present') or not r.get('rds_post_present')]
result={'at_utc':now(),'before':ids,'after':live,'replaced':victim,'elapsed_seconds':round(time.monotonic()-start,2),'sampled_requests':len(rows),'failed_samples':len(failures),'test_scope':'Planned ASG termination/replacement with connection draining; not an AZ outage or crash test'}
save('E15_replacement_summary.json',result);update(final_instances=live,replacement_verified_at=now());event('asg_replacement_verified',**result)
