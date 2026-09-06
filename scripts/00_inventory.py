"""Read-only starting inventory. Run in AWS CloudShell; outputs contain no credentials."""
import concurrent.futures
import datetime
import json
from pathlib import Path

import boto3
from botocore.config import Config

REGION = "ap-southeast-2"
OUT = Path.home() / "task3" / "evidence"
OUT.mkdir(parents=True, exist_ok=True)
SESSION = boto3.Session(region_name=REGION)
CONFIG = Config(retries={"max_attempts": 3, "mode": "standard"})

def read(service, operation, **kwargs):
    try:
        result = getattr(SESSION.client(service, config=CONFIG), operation)(**kwargs)
        result.pop("ResponseMetadata", None)
        return result
    except Exception as exc:
        return {"error": str(exc)}

checks = {
    "identity": ("sts", "get_caller_identity", {}),
    "iam_summary": ("iam", "get_account_summary", {}),
    "iam_users": ("iam", "list_users", {}),
    "vpcs": ("ec2", "describe_vpcs", {}),
    "subnets": ("ec2", "describe_subnets", {}),
    "instances": ("ec2", "describe_instances", {}),
    "key_pairs": ("ec2", "describe_key_pairs", {}),
    "rds": ("rds", "describe_db_instances", {}),
    "rds_mariadb_options": ("rds", "describe_orderable_db_instance_options", {
        "Engine": "mariadb", "DBInstanceClass": "db.t4g.micro", "MaxRecords": 100}),
    "load_balancers": ("elbv2", "describe_load_balancers", {}),
    "auto_scaling": ("autoscaling", "describe_auto_scaling_groups", {}),
    "s3": ("s3", "list_buckets", {}),
    "ssm_nodes": ("ssm", "describe_instance_information", {}),
    "ec2_quota": ("service-quotas", "get_service_quota", {
        "ServiceCode": "ec2", "QuotaCode": "L-1216C47A"}),
    "al2023": ("ssm", "get_parameter", {
        "Name": "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"}),
}
results = {"captured_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
           "region": REGION, "operation": "initial read-only inventory"}
with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
    jobs = {pool.submit(read, service, operation, **args): name
            for name, (service, operation, args) in checks.items()}
    for future in concurrent.futures.as_completed(jobs):
        results[jobs[future]] = future.result()
(OUT / "E01_initial_inventory.json").write_text(json.dumps(results, indent=2, default=str))
summary = {
    "time": results["captured_at_utc"], "region": REGION,
    "identity": results["identity"],
    "iam_summary": results["iam_summary"],
    "users": [u["UserName"] for u in results["iam_users"].get("Users", [])],
    "vpcs": [{k:v.get(k) for k in ("VpcId", "IsDefault", "CidrBlock")}
             for v in results["vpcs"].get("Vpcs", [])],
    "subnets": [{k:s.get(k) for k in ("SubnetId", "AvailabilityZone", "CidrBlock", "VpcId")}
                for s in results["subnets"].get("Subnets", [])],
    "existing_instances": sum(len(r["Instances"]) for r in results["instances"].get("Reservations", [])),
    "existing_rds": len(results["rds"].get("DBInstances", [])),
    "existing_albs": len(results["load_balancers"].get("LoadBalancers", [])),
    "existing_asgs": len(results["auto_scaling"].get("AutoScalingGroups", [])),
    "existing_buckets": [b["Name"] for b in results["s3"].get("Buckets", [])],
    "ec2_quota": results["ec2_quota"].get("Quota", {}),
    "ami": results["al2023"].get("Parameter", {}).get("Value"),
    "rds_versions": sorted({o["EngineVersion"] for o in results["rds_mariadb_options"].get("OrderableDBInstanceOptions", [])}),
    "errors": {name:r["error"] for name,r in results.items() if isinstance(r,dict) and "error" in r},
}
print(json.dumps(summary, indent=2, default=str))
print("INVENTORY_COMPLETE: ~/task3/evidence/E01_initial_inventory.json")
