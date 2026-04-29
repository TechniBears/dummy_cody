"""Phase 0 — BUDGET SAFETY LAMBDA.

Fires on CloudWatch billing alarm at 80% or 100% of the monthly budget.
Actions, in order:
  1. Set agent-cody/graph-sender-frozen to {"frozen": true, "reason": "<alarm>", "at": "<iso>"}.
     The graph-sender Lambda checks this flag on every invocation and bails out
     silently if frozen=true.
  2. Stop the Gateway EC2 instance (preserves EBS + tmpfs-wiped secrets).
  3. Publish to SNS so the operator is notified.

Rationale: this is the hard cap on surprise spend. A runaway loop, a rogue skill,
or a LLM edit-storm cannot continue burning dollars once 80% is breached.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

import boto3

logging.basicConfig(level=logging.INFO)
log = logging.getLogger()

REGION = os.environ["REGION"]
FROZEN_SECRET = os.environ["FROZEN_FLAG_SECRET"]
GW_INSTANCE_ID = os.environ["GW_INSTANCE_ID"]
SNS_TOPIC = os.environ["SNS_TOPIC"]


def handler(event: dict, context) -> dict:
    log.warning("graph-sender-freeze triggered event=%s", json.dumps(event, default=str))

    alarm_name = "unknown"
    if "alarmData" in event and "alarmName" in event["alarmData"]:
        alarm_name = event["alarmData"]["alarmName"]
    elif "AlarmName" in event:
        alarm_name = event["AlarmName"]

    now_iso = datetime.now(timezone.utc).isoformat()
    frozen_value = json.dumps({
        "frozen": True,
        "reason": f"billing_alarm:{alarm_name}",
        "at": now_iso,
    })

    sm = boto3.client("secretsmanager", region_name=REGION)
    sm.put_secret_value(SecretId=FROZEN_SECRET, SecretString=frozen_value)
    log.info("frozen flag set on %s", FROZEN_SECRET)

    ec2 = boto3.client("ec2", region_name=REGION)
    ec2.stop_instances(InstanceIds=[GW_INSTANCE_ID])
    log.info("stop_instances requested for %s", GW_INSTANCE_ID)

    sns = boto3.client("sns", region_name=REGION)
    sns.publish(
        TopicArn=SNS_TOPIC,
        Subject=f"[AGENT CODY] Graph sender FROZEN — {alarm_name}",
        Message=(
            f"Budget alarm '{alarm_name}' fired at {now_iso}.\n\n"
            f"Actions taken:\n"
            f"  1. Set {FROZEN_SECRET} = {{frozen: true}}.\n"
            f"  2. Stopped Gateway EC2 {GW_INSTANCE_ID}.\n\n"
            f"Manual unfreeze required. To resume:\n"
            f"  aws secretsmanager put-secret-value --secret-id {FROZEN_SECRET} "
            f"--secret-string '{{\"frozen\":false}}'\n"
            f"  aws ec2 start-instances --instance-ids {GW_INSTANCE_ID}\n"
        ),
    )

    return {
        "statusCode": 200,
        "body": json.dumps({"frozen": True, "stopped": GW_INSTANCE_ID}),
    }
