"""Method D - model & region discovery. Read-only inventory, no cost math.

Lists every AWS/Bedrock ModelId dimension visible in CloudWatch per region,
its rate-card class, and its inference profile (global vs regional). A model
that matches no rate-card row shows as UNMATCHED - that is how a new model
release gets noticed instead of silently mispriced.
"""
from __future__ import annotations

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from .. import pricing
from .cloudwatch import resolve_regions


def run(cw_kwargs, cfg, log, cancel=None):
    out = {"rows": [], "errors": [], "status": "ok"}
    regions, note = resolve_regions(cw_kwargs, cfg, log)
    if note:
        out["errors"].append(note)
    for region in regions:
        if cancel is not None and cancel.is_set():
            out["status"] = "cancelled"
            log("Cancelled by user.", "warn")
            return out
        try:
            cw = boto3.client("cloudwatch", region_name=region, **cw_kwargs)
            ids = set()
            for page in cw.get_paginator("list_metrics").paginate(
                    Namespace="AWS/Bedrock", MetricName="InputTokenCount"):
                for m in page.get("Metrics", []):
                    for d in m.get("Dimensions", []):
                        if d["Name"] == "ModelId":
                            ids.add(d["Value"])
        except (BotoCoreError, ClientError) as exc:
            out["errors"].append(f"{region}: {type(exc).__name__}: {exc}")
            log(f"  skipped {region}: {type(exc).__name__}", "warn")
            continue
        for mid in sorted(ids):
            hit = pricing.classify(mid)
            profile = "global" if pricing.is_global_profile(mid) else "regional"
            if hit:
                cls, label, rates = hit
                out["rows"].append({
                    "region": region, "model_id": mid, "class": cls,
                    "label": label, "profile": profile,
                    "rates": f"${rates['input']:g} / ${rates['output']:g}",
                })
            else:
                out["rows"].append({
                    "region": region, "model_id": mid, "class": "UNMATCHED",
                    "label": "(no rate-card row)", "profile": profile,
                    "rates": "-",
                })
        log(f"  {region}: {len(ids)} model id(s)")
    return out
