"""Produce real CPU load, retain metrics/alarm transitions, and restore standard credits."""
from task3lib import *
import requests
s=state();cw=client('cloudwatch');ssm=client('ssm');ec2=client('ec2');iid=s['AlarmInstance']
start=datetime.datetime.now(datetime.timezone.utc);prefix='E21_'+start.strftime('%Y%m%dT%H%M%SZ')
subscription=client('sns').list_subscriptions_by_topic(TopicArn=s['SnsTopic'])
save(prefix+'_subscription_at_test.json',subscription)
confirmed=any(x['SubscriptionArn']!='PendingConfirmation' for x in subscription['Subscriptions'])
spec=ec2.describe_instance_credit_specifications(InstanceIds=[iid]);save(prefix+'_initial_credit_mode.json',spec)
original=spec['InstanceCreditSpecifications'][0]['CpuCredits']
change=ec2.modify_instance_credit_specification(InstanceCreditSpecifications=[{'InstanceId':iid,'CpuCredits':'unlimited'}]);save(prefix+'_bounded_test_credit_mode.json',change)
assert not change.get('UnsuccessfulInstanceCreditSpecifications'),change
script='''#!/bin/bash
set -eu
date -Is
echo 'REAL_CPU_LOAD_START: two workers, 240 seconds, no synthetic metric injection'
timeout 270s python3 - <<'PY'
import multiprocessing,time,hashlib,datetime
def work():
    block=b'Task3 bounded CPU alarm verification'*2048
    while True: hashlib.sha256(block).digest()
workers=[multiprocessing.Process(target=work,daemon=True) for _ in range(2)]
for worker in workers:worker.start()
try:time.sleep(240)
finally:
    for worker in workers:worker.terminate()
    for worker in workers:worker.join()
print('Both load workers terminated',datetime.datetime.now(datetime.timezone.utc).isoformat())
PY
echo 'REAL_CPU_LOAD_END'
date -Is
'''
save(prefix+'_load_command.sh',script)
r=ssm.send_command(InstanceIds=[iid],DocumentName='AWS-RunShellScript',Parameters={'commands':[script],'executionTimeout':['300']},TimeoutSeconds=60,Comment='Task3 bounded real CPU alarm test')
command=r['Command']['CommandId'];event('real_cpu_load_started',instance=iid,command_id=command,duration_seconds=240,sns_confirmed=confirmed,evidence_prefix=prefix)
states=[];requests_log=[];previous=None;triggered=False;recovered=False;invocation=None
try:
    for _ in range(60):
        alarm=cw.describe_alarms(AlarmNames=[s['AlarmName']])['MetricAlarms'][0]
        state_row={'at_utc':now(),'state':alarm['StateValue'],'reason':alarm['StateReason'],'updated':str(alarm['StateUpdatedTimestamp'])};states.append(state_row)
        if state_row['state']!=previous:event('real_cpu_alarm_state',**state_row);previous=state_row['state']
        if alarm['StateValue']=='ALARM':triggered=True
        try:invocation=ssm.get_command_invocation(CommandId=command,InstanceId=iid)
        except ssm.exceptions.InvocationDoesNotExist:invocation=None
        if triggered and alarm['StateValue']=='OK' and invocation and invocation['Status']=='Success':recovered=True
        row={'at_utc':now()}
        try:
            resp=requests.get(s['final_url']+'/?alarm_check='+str(time.time_ns()),timeout=15,headers={'Connection':'close'})
            row.update(status=resp.status_code,node=resp.headers.get('X-Task3-Node'),baseline_present='Task 3 baseline record' in resp.text)
        except requests.RequestException as exc:row['error']=str(exc)
        requests_log.append(row)
        if recovered:break
        time.sleep(10)
finally:
    result=ec2.modify_instance_credit_specification(InstanceCreditSpecifications=[{'InstanceId':iid,'CpuCredits':original}]);save(prefix+'_restored_credit_mode.json',result)
    event('cpu_credit_mode_restored',instance=iid,mode=original)
    save(prefix+'_alarm_observations.json',states);save(prefix+'_public_requests.json',requests_log)
    if invocation:save(prefix+'_load_execution.json',invocation)
    save(prefix+'_alarm_history.json',cw.describe_alarm_history(AlarmName=s['AlarmName'],StartDate=start))
    for metric in ['CPUUtilization','CPUCreditBalance','CPUSurplusCreditBalance','CPUSurplusCreditsCharged']:
        metrics=cw.get_metric_statistics(Namespace='AWS/EC2',MetricName=metric,Dimensions=[{'Name':'InstanceId','Value':iid}],StartTime=start-datetime.timedelta(minutes=3),EndTime=datetime.datetime.now(datetime.timezone.utc),Period=60 if metric=='CPUUtilization' else 300,Statistics=['Average','Maximum'])
        save(prefix+'_'+metric+'.json',metrics)
result={'at_utc':now(),'triggered':triggered,'recovered':recovered,'load_status':invocation['Status'] if invocation else None,'sns_confirmed_at_test':confirmed,'public_samples':len(requests_log),'public_failures':sum(x.get('status')!=200 or not x.get('baseline_present') for x in requests_log),'evidence_prefix':prefix,'scope':'Real measured CPU alarm and recovery; email receipt requires separate mailbox evidence.'}
save(prefix+'_summary.json',result);event('cpu_alarm_test_result',**result)
assert triggered and recovered and result['load_status']=='Success',result
update(cpu_alarm_verified_at=now(),cpu_alarm_test_prefix=prefix,cpu_test_sns_confirmed=confirmed)
