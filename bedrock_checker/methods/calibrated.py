"""Method C - CE-calibrated estimate (notebook cell 8).

factor = CE actual / list-price estimate, per class, over trailing FINALIZED
days. Self-absorbs cache-TTL mix, Bedrock premium and region coverage. A class
with no finalized overlap gets factor 1.000 and is labelled uncalibrated -
never borrow another class's factor (Fable's premium is not Sonnet's).

Deviation from the notebook on purpose: per-class fresh-window raw totals are
summed from row-level costs (which already carry the correct per-model rate,
legacy SKUs included) instead of re-pricing aggregated tokens at one family
rate - the notebook's approach misprices a legacy/current mix within sonnet.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from .. import pricing
from . import cloudwatch


def _ce_daily_by_class(cw_kwargs, lookback_days):
    """{day: {class: $}} of actual billed cost from Cost Explorer."""
    ce = boto3.client("ce", region_name="us-east-1", **cw_kwargs)
    end = datetime.now(timezone.utc).date() + timedelta(days=1)
    start = end - timedelta(days=lookback_days + 2)
    resp = ce.get_cost_and_usage(
        TimePeriod={"Start": start.strftime("%Y-%m-%d"),
                    "End": end.strftime("%Y-%m-%d")},
        Granularity="DAILY", Metrics=["UnblendedCost"],
        GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}])
    out = {}
    for d in resp["ResultsByTime"]:
        day = d["TimePeriod"]["Start"]
        fam = {}
        for g in d["Groups"]:
            cls = pricing.classify_ce_service(g["Keys"][0])
            if not cls or cls == "other":
                continue
            fam[cls] = fam.get(cls, 0.0) + float(g["Metrics"]["UnblendedCost"]["Amount"])
        out[day] = fam
    return out


def _estimate_day_by_class(cw_kwargs, day, regions, cfg, log):
    """List-price estimate {class: $} for one UTC calendar day."""
    s = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    e = s + timedelta(days=1)
    fam = {}
    for region in regions:
        try:
            rows = cloudwatch.scan_region(region, cw_kwargs, s, e, cfg, log)
        except (BotoCoreError, ClientError):
            continue
        for r in rows:
            fam[r["class"]] = fam.get(r["class"], 0.0) + r["costs"]["total"]
    return fam


def run(hours, lookback_days, skip_recent_days, regions, cw_kwargs, cfg,
        classes, log, cancel=None):
    regions = regions or list(cfg.get("regions") or ["us-east-1"])
    log(f"Calibration regions: {regions}", "info")
    try:
        ce_daily = _ce_daily_by_class(cw_kwargs, lookback_days)
    except (BotoCoreError, ClientError) as exc:
        return {"status": f"ce_error: {type(exc).__name__}: {exc}"}

    cutoff = (datetime.now(timezone.utc).date()
              - timedelta(days=skip_recent_days)).strftime("%Y-%m-%d")
    log(f"Calibration over finalized days (<= {cutoff}):", "info")
    agg = {c: {"ce": 0.0, "est": 0.0} for c in classes}
    table = []
    for day in sorted(ce_daily):
        if day > cutoff:
            continue
        if cancel is not None and cancel.is_set():
            return {"status": "cancelled", "table": table}
        if max(ce_daily[day].values() or [0.0]) <= 0:
            continue
        est = _estimate_day_by_class(cw_kwargs, day, regions, cfg, log)
        for c in classes:
            ce = ce_daily[day].get(c, 0.0)
            es = est.get(c, 0.0)
            if ce <= 0 and es <= 0:
                continue
            agg[c]["ce"] += ce
            agg[c]["est"] += es
            # nan guard from the notebook: est==0 -> ratio excluded, shown n/a
            ratio = (ce / es) if es > 0 else None
            table.append({"day": day, "class": c, "estimate": es,
                          "ce": ce, "ratio": ratio})

    factors, calibrated = {}, {}
    for c in classes:
        if agg[c]["est"] > 0:
            factors[c] = agg[c]["ce"] / agg[c]["est"]
            calibrated[c] = True
        else:
            factors[c] = 1.0
            calibrated[c] = False

    res = cloudwatch.scan(hours=hours, regions=regions, cw_kwargs=cw_kwargs,
                          cfg=cfg, log=log, cancel=cancel)
    if res["status"] != "ok":
        return {"status": res["status"], "table": table, "factors": factors,
                "calibrated": calibrated}

    raw_totals = {}
    for r in res["rows"]:
        raw_totals[r["class"]] = raw_totals.get(r["class"], 0.0) + r["costs"]["total"]
    per_class = {c: {"raw": raw_totals.get(c, 0.0),
                     "calibrated": raw_totals.get(c, 0.0) * factors[c]}
                 for c in classes}
    return {"status": "ok", "table": table, "factors": factors,
            "calibrated": calibrated, "per_class": per_class,
            "window": (res["start"], res["end"])}
