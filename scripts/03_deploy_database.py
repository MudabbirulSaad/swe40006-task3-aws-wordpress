"""Provision private RDS while preserving the original local DB for migration proof."""
import secrets
from task3lib import *

s=state()
needed=("PrivateA","PrivateB","DbSG")
if not all(k in s for k in needed):
    resources=client("cloudformation").list_stack_resources(StackName=PREFIX+"-base")["StackResourceSummaries"]
    physical={r["LogicalResourceId"]:r.get("PhysicalResourceId") for r in resources if r["ResourceStatus"]=="CREATE_COMPLETE"}
    if not all(physical.get(k) for k in needed):raise RuntimeError("Database network is not ready")
    s=update(**{k:physical[k] for k in needed})
secret_path=PRIVATE/"database-master-password.txt"
if not secret_path.exists():secret_path.write_text(secrets.token_urlsafe(24))
password=secret_path.read_text()
client("ssm").put_parameter(Name="/swe40006/t3/migration/db-master",Value=password,Type="SecureString",Overwrite=True)
template={"AWSTemplateFormatVersion":"2010-09-09","Description":"Task 3 private single-AZ MariaDB; existing database migration follows verification of Pass",
    "Parameters":{"MasterPassword":{"Type":"String","NoEcho":True,"MinLength":8}},
    "Resources":{
        "DbSubnets":{"Type":"AWS::RDS::DBSubnetGroup","Properties":{"DBSubnetGroupName":PREFIX+"-db-subnets","DBSubnetGroupDescription":"Two private task subnets", "SubnetIds":[s["PrivateA"],s["PrivateB"]],"Tags":[{"Key":"Project","Value":PREFIX}]}},
        "Database":{"Type":"AWS::RDS::DBInstance","DeletionPolicy":"Snapshot","UpdateReplacePolicy":"Snapshot","Properties":{
            "DBInstanceIdentifier":PREFIX+"-db","Engine":"mariadb","EngineVersion":"10.11.19","DBInstanceClass":"db.t4g.micro",
            "AllocatedStorage":"20","StorageType":"gp3","StorageEncrypted":True,"MasterUsername":"t3master","MasterUserPassword":{"Ref":"MasterPassword"},
            "DBSubnetGroupName":{"Ref":"DbSubnets"},"VPCSecurityGroups":[s["DbSG"]],"PubliclyAccessible":False,"MultiAZ":False,
            "BackupRetentionPeriod":1,"AutoMinorVersionUpgrade":True,"CopyTagsToSnapshot":True,"DeletionProtection":False,
            "Tags":[{"Key":"Project","Value":PREFIX}]}}},
    "Outputs":{"DatabaseEndpoint":{"Value":{"Fn::GetAtt":["Database","Endpoint.Address"]}},"DatabaseId":{"Value":{"Ref":"Database"}}}}
deploy(PREFIX+"-database",template,{"MasterPassword":password})
outputs=wait_stack(PREFIX+"-database",timeout=1800)
update(**outputs)
save("E05_rds_configuration.json",client("rds").describe_db_instances(DBInstanceIdentifier=outputs["DatabaseId"]))
event("rds_created",outputs=outputs,migration_status="Not yet performed; original local DB remains authoritative")
