from task3lib import *
s=state();ids=s['final_instances'];iid=ids[-1]
# This monitored original member is not the selected replacement-test victim.
name=PREFIX+'-cpu-high'
alarm={'AlarmName':name,'AlarmDescription':'Task 3: EC2 average CPU exceeds 70% for two consecutive one-minute periods; SNS email on alarm and recovery. Retarget if this instance is later replaced.','ActionsEnabled':True,'AlarmActions':[s['SnsTopic']],'OKActions':[s['SnsTopic']],'MetricName':'CPUUtilization','Namespace':'AWS/EC2','Statistic':'Average','Dimensions':[{'Name':'InstanceId','Value':iid}],'Period':60,'EvaluationPeriods':2,'DatapointsToAlarm':2,'Threshold':70.0,'ComparisonOperator':'GreaterThanThreshold','TreatMissingData':'missing','Unit':'Percent','Tags':[{'Key':'Project','Value':PREFIX}]}
client('cloudwatch').put_metric_alarm(**alarm)
(IMPL/'infrastructure'/'cpu-alarm.json').write_text(json.dumps(alarm,indent=2))
save('E19_alarm_created.json',client('cloudwatch').describe_alarms(AlarmNames=[name]));update(AlarmName=name,AlarmInstance=iid)
event('cpu_alarm_configured',instance=iid,threshold_percent=70,period_seconds=60,evaluation_periods=2,topic=s['SnsTopic'])
