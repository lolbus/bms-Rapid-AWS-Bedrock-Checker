
![Rapid AWS Bedrock Cost Checker — A Buildman Shipped Project](personal_brand_materials/header_rapidawsbedrockchecker.png)

# Rapid Bedrock Cost Checker

*A Buildman Shipped Project.*

Are you facing challenges managing, tracking, and responding to billing matters related to AWS Bedrock as an AWS Administrator?

**Quickly download, deploy a Windows Tkinter app and assess what your AWS Bedrock Claude usage is costing you** — per
model class (sonnet / opus / fable / haiku / mythos), over any window from the
last hour to the last month. Portable Windows app: no Python, no installer, no
admin rights. Read-only: it only reads CloudWatch metrics and Cost Explorer
data; it cannot change anything in your AWS account.

## 1. Download & unzip

Get the latest zip from the release folder:

```
release/bedrock_checker_wins_v0.1.0_20260908.zip
```

Unzip the **whole** folder somewhere writable, e.g. `C:\tools\bedrock_checker`.
Keep all files together.

> **Tip:** right-click the zip → Properties → tick **Unblock** before
> extracting. On first launch Windows may say "Windows protected your PC"
> (the exe is unsigned) — click **More info → Run anyway**.
> `RELEASE_MANIFEST.json` carries sha256 hashes if you want to verify files.

## 2. Add your AWS keys (2 minutes)

You need a **read-only** IAM user. Minimum permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {"Effect": "Allow", "Action": ["cloudwatch:GetMetricData",
     "cloudwatch:GetMetricStatistics", "cloudwatch:ListMetrics"],
     "Resource": "*"},
    {"Effect": "Allow", "Action": "ce:GetCostAndUsage", "Resource": "*"},
    {"Effect": "Allow", "Action": "ec2:DescribeRegions", "Resource": "*"}
  ]
}
```

(`ec2:DescribeRegions` is optional — it only enables region auto-discovery.)

Then either:

- **Paste in the app** (easiest): run the app → **Settings** tab → paste
  Access key ID + Secret access key → **Save**. Keys land in `config.json`
  next to the exe — that file is now a secret; don't share the folder.
- **Or use environment variables** (nothing on disk):

  ```powershell
  setx EVAL_AWS_ACCESS_KEY_ID "AKIA..."
  setx EVAL_AWS_SECRET_ACCESS_KEY "..."
  ```

  Open a **new** window after `setx`. Prefer different variable names? Set
  them on the Settings tab under "...or env var for ...".

## 3. Run

Double-click **`run_bedrock_checker.bat`**.

## 4. Which tab answers your question

| You want to know... | Use this tab | Keep in mind |
|---|---|---|
| **What did AWS actually bill us?** | **Cost Explorer (billed)** | The truth. Daily grain, lags 1–2 days — today/yesterday show `$0 est` until AWS finalizes. |
| **What are we spending RIGHT NOW / last N hours?** | **CloudWatch estimate** | Fresh within minutes, but a list-price estimate (can run ~10–30% off the final bill). |
| **Fresh numbers that track the real bill?** | **CE-calibrated** | Corrects the estimate using your recent finalized bills. Best of both. |
| **Is any model unpriced / newly appeared?** | **Discovery** | Inventory of every Bedrock model seen. `UNMATCHED` = new model, rate card needs a row. |
| Change defaults, keys, regions | **Settings** | Everything is stored in `config.json`. |

**Typical flow:** Cost Explorer for the weekly/monthly bill → CloudWatch
estimate with hours = 24 (or 1–6 right after a big test run) for "what did
that just cost us?" → CE-calibrated when the fresh number has to be
budget-grade.

## 5. Reading the result

Every run ends with the rollup — cost per model class, always all five, even
when zero:

```
Usage analysis result:
USD$0.00 sonnet
USD$103.84 opus
USD$0.80 fable
USD$0.00 haiku
USD$0.00 mythos
```

In the Cost Explorer tab, `final` means AWS has finalized that day, `est`
means it can still move. Detail rows show the exact model IDs and regions that
contributed, so you can tell `claude-sonnet-4-5` in `us-east-1` from
`claude-3-5-sonnet` in `ap-southeast-1` (they bill at different rates).

## 6. Settings worth knowing

| Setting | What it does |
|---|---|
| **Hours back** | The trace window. Set per run on each tab; default in Settings. |
| **Regions** | Comma-separated list; auto-discover scans all enabled regions (slower, needs `ec2:DescribeRegions`). |
| **Cache write TTL** | `5m` (default) or `1h` — pick what your workloads actually use; it changes the estimate. |
| **Regional premium %** | Regional inference profiles bill ~10% above `global.` ones. Default 10. |

## 7. Troubleshooting

| Symptom | Fix |
|---|---|
| "No credentials found" | Settings tab → paste keys → Save; or set the env vars and restart the app. |
| Cost Explorer tab errors | The IAM principal lacks `ce:GetCostAndUsage` — add it (policy above). |
| Everything shows $0 | CloudWatch lags a few minutes — wait 2–5 min and re-run. Check the regions list. CE shows $0 for today/yesterday by design. |
| Window doesn't open | Run `run_bedrock_checker.bat` from a terminal to see the error. |
| AV quarantines the exe | Ask whoever built it for a UPX-off rebuild. |

**Privacy:** keys stay on your machine. The app makes only outbound HTTPS
calls to AWS read-only APIs and binds no network port.

---

## For developers

```bat
uv sync --dev
uv run python -m bedrock_checker            REM run from source
uv run python build_module\smoke_test.py    REM offline sanity checks
uv run python build_module\live_check.py    REM read-only live account check
python build_module\build_and_release.py    REM build exe + assemble + zip
python verify_release.py release\bedrock_checker_wins_v0.1.0 --require-tk --zip release\<zip>
```

Ported from `../check_hrs_bedrock_usage.ipynb` (one tab per method).
