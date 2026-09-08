"""Method A - Cost Explorer: ACTUAL billed USD (notebook cell 6).

UnblendedCost is what AWS truly billed. Caveats carried over from the notebook:
daily granularity, lags ~1-2 days (today/yesterday read $0 'est'), Claude bills
as AWS Marketplace '...(Amazon Bedrock Edition)' products, ce is us-east-1-only
and ~$0.01/call, and the IAM principal needs ce:GetCostAndUsage.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from ..pricing import classify_ce_service


def _is_anthropic_service(name: str) -> bool:
    n = name.lower()
    return (("bedrock edition" in n) or ("claude" in n)
            or ("anthropic" in n and "bedrock" in n))


def report(days, granularity, cw_kwargs, log):
    ce = boto3.client("ce", region_name="us-east-1", **cw_kwargs)
    end = datetime.now(timezone.utc).date() + timedelta(days=1)  # CE End exclusive
    start = end - timedelta(days=int(days) + 1)
    log(f"Cost Explorer {start} -> {end} UTC (End exclusive), "
        f"granularity={granularity}...", "info")
    try:
        resp = ce.get_cost_and_usage(
            TimePeriod={"Start": start.strftime("%Y-%m-%d"),
                        "End": end.strftime("%Y-%m-%d")},
            Granularity=granularity, Metrics=["UnblendedCost"],
            GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
        )
    except (BotoCoreError, ClientError) as exc:
        return {"status": f"ce_error: {type(exc).__name__}: {exc}"}
    rows = []
    for d in resp["ResultsByTime"]:
        day = d["TimePeriod"]["Start"]
        flag = "est" if d.get("Estimated") else "final"
        for g in d["Groups"]:
            name = g["Keys"][0]
            if not _is_anthropic_service(name):
                continue
            amt = float(g["Metrics"]["UnblendedCost"]["Amount"])
            if amt == 0:
                continue
            cls = classify_ce_service(name) or "other"
            rows.append({"day": day, "service": name, "amount": amt,
                         "flag": flag, "class": cls})
    return {"status": "ok", "rows": rows, "start": str(start), "end": str(end)}
