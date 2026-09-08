"""Method B - CloudWatch list-price estimate (notebook cells 2-3).

Reads AWS-recorded token counts from the AWS/Bedrock namespace and prices them
with the built-in rate card. Uses ONE batched get_metric_data call per region
(<=500 MetricDataQueries) instead of the notebook's 4 get_metric_statistics
calls per model - same numbers, far fewer API calls.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from .. import pricing

CW_METRICS = {
    "input": "InputTokenCount",
    "output": "OutputTokenCount",
    "cache_read": "CacheReadInputTokenCount",
    "cache_write": "CacheWriteInputTokenCount",
}

FALLBACK_REGIONS = ["us-east-1", "us-west-2", "eu-central-1", "eu-west-1",
                    "ap-southeast-1", "ap-southeast-2", "ap-northeast-1"]


def resolve_regions(cw_kwargs, cfg, log):
    """Configured regions, or ec2:DescribeRegions when auto-discover is on."""
    if not cfg.get("auto_discover_regions") and cfg.get("regions"):
        return list(cfg["regions"]), None
    try:
        ec2 = boto3.client("ec2", region_name="us-east-1", **cw_kwargs)
        regions = sorted(r["RegionName"] for r in ec2.describe_regions()["Regions"])
        return regions, None
    except (BotoCoreError, ClientError) as exc:
        log(f"NOTE: ec2:DescribeRegions denied ({type(exc).__name__}); "
            f"using fixed list {FALLBACK_REGIONS}", "warn")
        return list(FALLBACK_REGIONS), f"describe_regions denied: {type(exc).__name__}"


def list_model_ids(cw, include_unmatched=False):
    """Every ModelId dimension visible under AWS/Bedrock in one region."""
    ids = set()
    paginator = cw.get_paginator("list_metrics")
    for page in paginator.paginate(Namespace="AWS/Bedrock",
                                   MetricName="InputTokenCount"):
        for m in page.get("Metrics", []):
            for d in m.get("Dimensions", []):
                if d["Name"] != "ModelId":
                    continue
                if pricing.classify(d["Value"]) or include_unmatched:
                    ids.add(d["Value"])
    return sorted(ids)


def _queries_for(model_ids, period):
    queries, index = [], {}
    i = 0
    for mid in model_ids:
        for key, metric in CW_METRICS.items():
            qid = f"q{i}"
            i += 1
            index[qid] = (mid, key)
            queries.append({
                "Id": qid,
                "ReturnData": True,
                "MetricStat": {
                    "Metric": {
                        "Namespace": "AWS/Bedrock",
                        "MetricName": metric,
                        "Dimensions": [{"Name": "ModelId", "Value": mid}],
                    },
                    "Period": period,
                    "Stat": "Sum",
                },
            })
    return queries, index


def scan_region(region, cw_kwargs, start, end, cfg, log):
    """Per-model token rows for one region via batched GetMetricData."""
    cw = boto3.client("cloudwatch", region_name=region, **cw_kwargs)
    model_ids = list_model_ids(cw)
    if not model_ids:
        return []
    period = int(cfg.get("cloudwatch_period_s", 3600))
    queries, index = _queries_for(model_ids, period)
    totals = {mid: {k: 0 for k in CW_METRICS} for mid in model_ids}
    for off in range(0, len(queries), 500):
        chunk = queries[off:off + 500]
        kwargs = {"MetricDataQueries": chunk, "StartTime": start, "EndTime": end,
                  "ScanBy": "TimestampAscending"}
        while True:
            resp = cw.get_metric_data(**kwargs)
            for series in resp.get("MetricDataResults", []):
                mid, key = index[series["Id"]]
                totals[mid][key] += int(sum(series.get("Values", [])))
            nxt = resp.get("NextToken")
            if not nxt:
                break
            kwargs["NextToken"] = nxt
    rows = []
    premium = float(cfg.get("regional_premium_pct", 10))
    for mid in model_ids:
        t = totals[mid]
        if sum(t.values()) <= 0:
            continue
        cls, label, rates = pricing.classify(mid)
        glob = pricing.is_global_profile(mid)
        row = {"region": region, "model_id": mid, "class": cls, "label": label,
               "global": glob, "premium_pct": 0.0 if glob else premium, **t}
        row["costs"] = pricing.cost_breakdown(
            t, rates, cfg.get("cache_write_ttl", "5m"), row["premium_pct"])
        rows.append(row)
    return rows


def scan(hours=None, start=None, end=None, regions=None, cw_kwargs=None,
         cfg=None, log=print, cancel=None):
    """Sum Claude Bedrock token usage over [start, end] (or last `hours`)."""
    out = {"rows": [], "regions_scanned": [], "errors": [], "status": "ok",
           "start": None, "end": None}
    if end is None:
        end = datetime.now(timezone.utc)
    if start is None:
        start = end - timedelta(hours=float(hours or 24))
    out["start"], out["end"] = start, end
    # Pad to bucket boundaries; CloudWatch buckets to the minute, Bedrock lags.
    q_start = (start - timedelta(minutes=1)).replace(second=0, microsecond=0)
    q_end = (end + timedelta(minutes=5)).replace(second=0, microsecond=0)

    if regions is None:
        regions, note = resolve_regions(cw_kwargs, cfg, log)
        if note:
            out["errors"].append({"region": "(discovery)", "error": note})
    log(f"Scanning {len(regions)} region(s) "
        f"[{q_start:%Y-%m-%d %H:%M} -> {q_end:%Y-%m-%d %H:%M} UTC]...", "info")
    for region in regions:
        if cancel is not None and cancel.is_set():
            out["status"] = "cancelled"
            log("Cancelled by user.", "warn")
            return out
        try:
            rows = scan_region(region, cw_kwargs, q_start, q_end, cfg, log)
        except (BotoCoreError, ClientError) as exc:
            out["errors"].append({"region": region,
                                  "error": f"{type(exc).__name__}: {exc}"})
            log(f"  skipped {region}: {type(exc).__name__}", "warn")
            continue
        if rows:
            out["regions_scanned"].append(region)
            out["rows"].extend(rows)
            log(f"  {region}: {len(rows)} model(s) with usage")
    return out
