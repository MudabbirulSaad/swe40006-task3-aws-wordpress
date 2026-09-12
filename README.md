# WordPress deployment on AWS

SWE40006 Software Deployment and Evolution - Task 3, Semester 2, 2026.

This repository contains the infrastructure and scripts used to move WordPress from a single EC2 instance with a local database to two web instances behind an Application Load Balancer, using a private RDS database.

The deployment was tested on 12 September 2026 in `ap-southeast-2`. Screenshots, command output and test results are included in the accompanying PDF report.

## Architecture

```text
Browser -> Application Load Balancer -> WordPress EC2 instances -> RDS MariaDB
                                       ap-southeast-2a and 2b

S3                Application backup and release archive
Parameter Store   Private WordPress configuration
Session Manager   Terminal access without inbound SSH
CloudWatch + SNS  CPU alarm and notification configuration
```

The web instances use Amazon Linux 2023, Apache, PHP and WordPress 7.1. The Auto Scaling group has minimum and desired capacity two, with maximum capacity four. Backend HTTP is accepted only from the load balancer, and the database accepts connections only from the web security group in the final configuration.

## Files

| Location | Purpose |
|---|---|
| `scripts/` | Python provisioning and verification scripts, plus the Bash installation, migration and restore scripts |
| `infrastructure/swe40006-t3-*.json` | The four generated CloudFormation templates for the network, database, load balancer and scaling group |
| `infrastructure/*-runtime-policy.json` | Runtime permissions for the original server and final web instances |
| `infrastructure/cpu-alarm.json` | CloudWatch alarm configuration |
| `requirements.txt` | Python dependencies used for the deployment |

The generated JSON files contain identifiers from the recorded deployment. They show the deployed configuration; they are not portable input files for another AWS account. The Python scripts generate the relevant values for their deployment stages.

## Local setup

Install the dependencies in a Python 3.12 environment:

```sh
python -m pip install -r requirements.txt
```

The scripts expect this checkout to be named `05_implementation`, with `04_evidence/logs/` and `.private/` in its parent folder. These paths are defined in [`scripts/task3lib.py`](scripts/task3lib.py). Expand the setup details before running a stage.

<details>
<summary>Workspace layout and AWS setup</summary>

```text
task3/
  05_implementation/        This repository
  04_evidence/logs/         Local execution results and deployment state
  .private/                Local credentials and configuration
```

Create `04_evidence/logs/` and `.private/` before running a local stage. All paths below are relative to the `task3/` workspace unless stated otherwise.

The local runner reads `.private/task3-operator-credentials.json`, containing the boto3 fields `aws_access_key_id`, `aws_secret_access_key` and `region_name`. It reads the notification address from `.private/alert-email.txt`. These files stay outside the repository.

Scripts `00` and `01` run in AWS CloudShell using an existing AWS account. The access bootstrap creates the task operator and budget; it writes credentials to `~/task3-private/` and takes the notification address from `TASK3_ALERT_EMAIL`. If using that bootstrap, transfer its credentials securely into the local private directory. The later stages use the operator credentials. The account-owner setup also needs the service-linked roles required by RDS, Elastic Load Balancing and Auto Scaling.

</details>

## Deployment stages

The numbered scripts record the order of the work. Run and verify each stage separately; several stages change infrastructure or application data. They use the local deployment-state file and are not a single-command installer or a general update tool for an existing environment.

| Stage | Scripts |
|---|---|
| Inventory and access | `00_inventory.py`, `01_access_bootstrap.py` |
| EC2, local WordPress and private RDS | `02_deploy_pass.py`, `03_deploy_database.py`, `04_verify_pass.py` |
| Runtime permissions and SNS | `05_prepare_credit.py` |
| Database migration | `06_migrate_rds.py`, `migrate-rds.sh` |
| S3 backup and restore | `08_backup_restore.py`, `backup-restore.sh` |
| WordPress AMI | `09_build_image.py`, `bootstrap-builder.sh` |
| ALB and Auto Scaling | `10_create_alb.py`, `11_create_asg.py`, `bootstrap-web.sh` |
| Application and replacement tests | `12_verify_scaling.py`, `13_replace_backend.py` |
| CPU monitoring and load test | `14_create_alarm.py`, `15_test_cpu_alarm.py` |
| Final access rules and checks | `16_finalize_security.py`, `17_final_audit.py` |

`task3lib.py` provides the shared AWS clients, state handling and command execution. `bootstrap-pass.sh` installs the initial application. The baseline post is created during application setup and checked again after migration.

Two recovery files are retained because they explain issues encountered during the work. `recover-pass-memory.sh` addresses the PHP memory limit during WordPress extraction. `07_finish_migration.py` resumes validation after a command-line check failed following a successful import. These are conditional recovery steps, not extra imports to run after every migration.

The last audit script also expects the private database and WordPress passwords saved during the original execution. Review its inputs before using it in a different environment.

## Results and limitations

The migration matched all 12 database table counts and the post records. The S3 restore passed its checksum, file comparison and application-content checks. During planned instance replacement, all 43 sampled requests succeeded and the replacement joined the healthy pair in 95.44 seconds. Both final instances accepted new Session Manager connections with SSH ingress removed.

A real CPU workload triggered the CloudWatch alarm and it later returned to OK. Email receipt remained unverified because the SNS subscription was awaiting confirmation at the final recorded check.

The deployment uses public HTTP and a single-AZ database. The file restore used a separate directory on the existing EC2 instance. Additional scale-out was not tested within the account's five-vCPU quota. The alarm monitors one instance ID and needs updating when that instance is replaced.

## Resource management

The stages create chargeable AWS resources. The budget sends notifications and does not stop spending. Stopping an Auto Scaling member can trigger its replacement; manage group capacity when pausing the web tier. Storage, the ALB and other retained resources can still incur charges. Preserve the database, application archive and private configuration before any cleanup.

Credentials, private keys, database dumps, raw execution logs, course documents and the report are not stored in this repository.
