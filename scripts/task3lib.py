"""Local task runner helpers: private authentication, durable state and real test logs."""
import datetime
import json
import shutil
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".runtime"))
import boto3
from botocore.config import Config

REGION = "ap-southeast-2"
PREFIX = "swe40006-t3"
LOGS = ROOT / "04_evidence" / "logs"
PRIVATE = ROOT / ".private"
IMPL = ROOT / "05_implementation"
STATE_FILE = LOGS / "deployment-state.json"
CONFIG = Config(retries={"max_attempts": 5, "mode": "standard"})
SESSION = boto3.Session(**json.loads((PRIVATE / "task3-operator-credentials.json").read_text()))

def client(service):
    return SESSION.client(service, config=CONFIG)

def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def save(name, data):
    path=LOGS/name
    if path.exists():
        history=LOGS/'history'
        history.mkdir(exist_ok=True)
        shutil.copy2(path,history/(path.stem+'_before_'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+path.suffix))
    path.write_text(json.dumps(data,indent=2,default=str) if not isinstance(data,str) else data,encoding="utf-8")
    return path

def state():
    return json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {"region":REGION,"prefix":PREFIX}

def update(**fields):
    value=state()
    value.update(fields)
    STATE_FILE.write_text(json.dumps(value,indent=2),encoding="utf-8")
    return value

def event(action, **details):
    row={"at_utc":now(),"actor":"Codex-assisted task operator","action":action,**details}
    with (LOGS/"execution-events.jsonl").open("a",encoding="utf-8") as stream:
        stream.write(json.dumps(row,default=str)+"\n")
    print(json.dumps(row,default=str),flush=True)

def stack_outputs(name):
    stack=client("cloudformation").describe_stacks(StackName=name)["Stacks"][0]
    return stack, {x["OutputKey"]:x["OutputValue"] for x in stack.get("Outputs",[])}

def deploy(name, template, parameters=None):
    cf=client("cloudformation")
    text=json.dumps(template,indent=2)
    (IMPL/"infrastructure"/(name+".json")).write_text(text,encoding="utf-8")
    cf.validate_template(TemplateBody=text)
    try:
        existing,_=stack_outputs(name)
    except cf.exceptions.ClientError as exc:
        if "does not exist" not in str(exc):raise
        existing=None
    kwargs={"StackName":name,"TemplateBody":text,"Capabilities":["CAPABILITY_NAMED_IAM"],
            "Tags":[{"Key":"Project","Value":PREFIX}]}
    if parameters:kwargs["Parameters"]=[{"ParameterKey":k,"ParameterValue":str(v)} for k,v in parameters.items()]
    if existing:
        event("stack_already_exists",stack=name,status=existing["StackStatus"])
        return
    result=cf.create_stack(**kwargs,OnFailure="DO_NOTHING")
    event("create_stack",stack=name,stack_id=result["StackId"],template_file=str(IMPL/"infrastructure"/(name+".json")))

def wait_stack(name, timeout=1200):
    start=time.monotonic()
    previous=None
    while time.monotonic()-start<timeout:
        stack,outputs=stack_outputs(name)
        status=stack["StackStatus"]
        if status!=previous:event("stack_status",stack=name,status=status)
        previous=status
        if status in ("CREATE_COMPLETE", "UPDATE_COMPLETE"):
            save(name+"-events.json",client("cloudformation").describe_stack_events(StackName=name))
            return outputs
        if "FAILED" in status or "ROLLBACK" in status:
            details=client("cloudformation").describe_stack_events(StackName=name)
            save(name+"-events.json",details)
            raise RuntimeError(json.dumps([e for e in details["StackEvents"] if "FAILED" in e["ResourceStatus"]],default=str))
        time.sleep(10)
    raise TimeoutError(name)

def run_ssm(instance, commands, evidence_name, timeout=600, print_output=True):
    """Record execution and output. Commands must refer to secrets without including values."""
    ssm=client("ssm")
    result=ssm.send_command(InstanceIds=[instance],DocumentName="AWS-RunShellScript",
        Parameters={"commands":[commands],"executionTimeout":[str(timeout)]},TimeoutSeconds=60,
        Comment=evidence_name[:100])
    command=result["Command"]["CommandId"]
    event("ssm_run_command",instance=instance,command_id=command,evidence=evidence_name)
    save(evidence_name+"-command.sh",commands)
    start=time.monotonic()
    while time.monotonic()-start<timeout+90:
        try:r=ssm.get_command_invocation(CommandId=command,InstanceId=instance)
        except ssm.exceptions.InvocationDoesNotExist:
            time.sleep(2);continue
        if r["Status"] not in ("Pending","InProgress","Delayed"):
            save(evidence_name+".json",r)
            save(evidence_name+".log",r.get("StandardOutputContent","")+"\nSTDERR:\n"+r.get("StandardErrorContent",""))
            event("ssm_result",instance=instance,command_id=command,status=r["Status"],exit_code=r.get("ResponseCode"),evidence=evidence_name)
            if print_output: print(r.get("StandardOutputContent","")[-14000:],flush=True)
            if r["Status"]!="Success":raise RuntimeError(r.get("StandardErrorContent","")+r.get("StandardOutputContent",""))
            return r
        time.sleep(3)
    raise TimeoutError(command)
