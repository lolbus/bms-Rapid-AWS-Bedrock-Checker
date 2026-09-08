# Bedrock Cost Checker v0.1.0

Quickly assess what your AWS Bedrock Claude usage is costing you. Portable -
no Python, no installer, no admin rights. Read-only: the app only ever reads
CloudWatch metrics and Cost Explorer data; it cannot change anything in your
AWS account.

## 1. Unzip

Unzip the WHOLE folder somewhere writable, e.g. `C:\tools\bedrock_checker`.
Keep all files together.

Tip: right-click the zip -> Properties -> tick **Unblock** before extracting.
On first launch Windows may show "Windows protected your PC" (the exe is
unsigned) - click **More info -> Run anyway**. `RELEASE_MANIFEST.json` has
sha256 hashes if you want to verify the files.

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

(`ec2:DescribeRegions` is optional - it only enables region auto-discovery.)

Then either:

- **Paste in the app** (easiest): run the app -> **Settings** tab -> paste
  Access key ID + Secret access key -> **Save**. Keys are stored in
  `config.json` next to the exe - that file is now a secret, don't share the
  folder.
- **Or use environment variables** (nothing on disk):

  ```powershell
  setx EVAL_AWS_ACCESS_KEY_ID "AKIA..."
  setx EVAL_AWS_SECRET_ACCESS_KEY "..."
  ```

  Open a NEW window after `setx`. Different env var names? Set them on the
  Settings tab under "...or env var for ...".

## 3. Run

Double-click **`run_bedrock_checker.bat`**.

## 4. Which tab answers your question

| You want to know... | Use this tab | Keep in mind |
|---|---|---|
| **What did AWS actually bill us?** | **Cost Explorer (billed)** | The truth. Daily grain, lags 1-2 days - today/yesterday show `$0 est` until AWS finalizes. |
| **What are we spending RIGHT NOW / last N hours?** | **CloudWatch estimate** | Fresh within minutes, but a list-price estimate (can run ~10-30% off the final bill). |
| **Fresh numbers that track the real bill?** | **CE-calibrated** | Corrects the estimate using your recent finalized bills. Best of both. |
| **Is any model unpriced / newly appeared?** | **Discovery** | Inventory of every Bedrock model seen. `UNMATCHED` = new model, rate card needs a row. |
| Change defaults, keys, regions | **Settings** | Everything is stored in `config.json`. |

Typical flow: **Cost Explorer** for the monthly/weekly bill, **CloudWatch
estimate** with hours = 24 (or 1-6 after a big test run) for "what did that
just cost us?", **CE-calibrated** when you need the fresh number to be
budget-grade.

## 5. Reading the result

Every run ends with the rollup - cost per model class, always all five, even
when zero:

```
Usage analysis result:
USD$0.00 sonnet
USD$103.84 opus
USD$0.80 fable
USD$0.00 haiku
USD$0.00 mythos
```

In the Cost Explorer tab, `final` = AWS has finalized that day, `est` = still
moving. Rows also show the exact model IDs and regions that contributed.

## 6. Settings worth knowing

- **Hours back** - the trace window (per run on each tab; default in Settings).
- **Regions** - comma-separated; auto-discover scans all enabled regions
  (slower, needs `ec2:DescribeRegions`).
- **Cache write TTL** - 5m (default) or 1h; pick what your workloads use.
- **Regional premium %** - regional inference profiles cost ~10% more than
  `global.` ones; default 10.

## 7. Troubleshooting

| Symptom | Fix |
|---|---|
| "No credentials found" | Settings tab: paste keys + Save, or set the env vars and restart the app. |
| Cost Explorer tab errors | IAM principal lacks `ce:GetCostAndUsage` - add it (policy above). |
| Everything shows $0 | CloudWatch lags a few minutes - wait 2-5 min and re-run; check the regions list; CE shows $0 for today/yesterday by design. |
| Window doesn't open | Run `run_bedrock_checker.bat` from a terminal to see the error. |
| AV quarantines the exe | Ask whoever built it for a UPX-off rebuild. |

Privacy: keys stay on your machine. The app makes only outbound HTTPS calls to
AWS read-only APIs. It binds no network port.
