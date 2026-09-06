"""One-time account-owner bootstrap for a named Task 3 operator and usage budget.

Run in the already authorised CloudShell session. Credentials are saved privately,
never printed. The account is on the Free plan; this script does not upgrade it.
"""
import configparser
import datetime
import json
import os
from pathlib import Path
import boto3

os.umask(0o077)
region = "ap-southeast-2"
prefix = "swe40006-t3"
session = boto3.Session(region_name=region)
iam = session.client("iam")
account = session.client("sts").get_caller_identity()["Account"]
private = Path.home() / "task3-private"
private.mkdir(exist_ok=True)
email = os.environ.get('TASK3_ALERT_EMAIL')
if not email:
    raise RuntimeError('Set TASK3_ALERT_EMAIL to the authorised notification address before running bootstrap.')
evidence = Path.home() / "task3" / "evidence"
evidence.mkdir(parents=True, exist_ok=True)
user = prefix + "-operator"
try:
    iam.get_user(UserName=user)
except iam.exceptions.NoSuchEntityException:
    iam.create_user(UserName=user, Tags=[{"Key":"Project","Value":prefix}])

# Project provisioning permissions, limited to this region and the service families
# needed for the task. IAM role/profile and S3 write permissions are name-scoped.
# The account was inventoried as empty; no IAM administrator policy is attached.
policy = {"Version":"2012-10-17","Statement":[
    {"Sid":"RegionalTaskServices","Effect":"Allow","Action":[
        "ec2:*","rds:*","elasticloadbalancing:*","autoscaling:*",
        "cloudformation:*","cloudwatch:*","sns:*","ssm:*"],
     "Resource":"*","Condition":{"StringEquals":{"aws:RequestedRegion":region}}},
    {"Sid":"ProjectBuckets","Effect":"Allow","Action":"s3:*",
     "Resource":[f"arn:aws:s3:::{prefix}-*",f"arn:aws:s3:::{prefix}-*/*"]},
    {"Sid":"S3List","Effect":"Allow","Action":"s3:ListAllMyBuckets","Resource":"*"},
    {"Sid":"TaskRoleAndProfileManagement","Effect":"Allow","Action":[
        "iam:CreateRole","iam:GetRole","iam:DeleteRole","iam:TagRole",
        "iam:PutRolePolicy","iam:GetRolePolicy","iam:DeleteRolePolicy","iam:ListRolePolicies",
        "iam:AttachRolePolicy","iam:DetachRolePolicy","iam:ListAttachedRolePolicies",
        "iam:CreateInstanceProfile","iam:GetInstanceProfile","iam:DeleteInstanceProfile",
        "iam:AddRoleToInstanceProfile","iam:RemoveRoleFromInstanceProfile","iam:PassRole"],
     "Resource":[f"arn:aws:iam::{account}:role/{prefix}-*",
                 f"arn:aws:iam::{account}:instance-profile/{prefix}-*"]},
    {"Sid":"ReadOwnIdentityAndQuotas","Effect":"Allow","Action":[
        "sts:GetCallerIdentity","iam:GetUser","iam:ListUsers","iam:GetAccountSummary",
        "servicequotas:GetServiceQuota","pricing:GetProducts"],"Resource":"*"}
]}
iam.put_user_policy(UserName=user,PolicyName=prefix+"-deployment",PolicyDocument=json.dumps(policy))
credentials_file = private / "task3-operator-credentials.json"
if not credentials_file.exists():
    if iam.list_access_keys(UserName=user)["AccessKeyMetadata"]:
        raise RuntimeError("Operator has a key but the private file is absent; do not create duplicate keys.")
    key=iam.create_access_key(UserName=user)["AccessKey"]
    credentials_file.write_text(json.dumps({"aws_access_key_id":key["AccessKeyId"],
        "aws_secret_access_key":key["SecretAccessKey"],"region_name":region}))
    credentials_file.chmod(0o600)
creds=json.loads(credentials_file.read_text())
aws_dir=Path.home()/".aws"
aws_dir.mkdir(exist_ok=True)
cfg=configparser.RawConfigParser()
cfg.read(aws_dir/"credentials")
if not cfg.has_section("task3"):cfg.add_section("task3")
for k in ("aws_access_key_id","aws_secret_access_key"):cfg.set("task3",k,creds[k])
with (aws_dir/"credentials").open("w") as stream:cfg.write(stream)
(aws_dir/"credentials").chmod(0o600)

budget_result="not attempted"
budgets=session.client("budgets",region_name="us-east-1")
try:
    budgets.describe_budget(AccountId=account,BudgetName=prefix+"-usage")
    budget_result="existing budget retained"
except budgets.exceptions.NotFoundException:
    budgets.create_budget(AccountId=account,Budget={
        "BudgetName":prefix+"-usage","BudgetType":"COST","TimeUnit":"MONTHLY",
        "BudgetLimit":{"Amount":"20","Unit":"USD"},
        "CostTypes":{"IncludeCredit":False,"IncludeRefund":False}},
        NotificationsWithSubscribers=[{"Notification":{
            "NotificationType":"ACTUAL","ComparisonOperator":"GREATER_THAN",
            "Threshold":threshold,"ThresholdType":"ABSOLUTE_VALUE"},
            "Subscribers":[{"SubscriptionType":"EMAIL","Address":email}]}
            for threshold in (10,20)])
    budget_result="created: USD20 monthly gross-usage budget; notifications at USD10 and USD20"
operator=boto3.Session(**creds)
identity=operator.client("sts").get_caller_identity()
identity.pop("ResponseMetadata",None)
result={"time_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "operator_identity":identity,"policy_scope":"Task services in Sydney; project-named IAM roles/profiles and S3 buckets",
        "credentials":"Saved privately; not included in evidence or source code",
        "budget":budget_result,"budget_is_hard_cap":False,
        "account_plan":"Free plan retained; no upgrade requested"}
(evidence/"E01_operator_and_budget.json").write_text(json.dumps(result,indent=2))
(evidence/"E01_operator_policy.json").write_text(json.dumps(policy,indent=2))
print(json.dumps(result,indent=2))
print("ACCESS_BOOTSTRAP_COMPLETE")
