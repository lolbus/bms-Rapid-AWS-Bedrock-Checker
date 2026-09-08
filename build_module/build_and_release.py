#!/usr/bin/env python
"""One-command release pipeline for bedrock_checker_wins.

    python build_module\\build_and_release.py            # full pipeline
    python build_module\\build_and_release.py --skip-build   # reuse dist/

Steps: version agreement check (BEFORE any PyInstaller run) -> build_exe.bat ->
assemble release folder (config.json keep_existing) -> RELEASE_MANIFEST.json ->
zip the folder. Stdlib only. Run from anywhere; paths resolve from this file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

APP_NAME = "bedrock_checker_wins"
VERSION = "0.1.0"
EXE_NAME = f"{APP_NAME}.exe"
ROOT = Path(__file__).resolve().parent.parent

RUN_BAT = r"""@echo off
REM {APP_NAME} v{VERSION} -- portable launcher.
REM chcp 65001 first: the exe logs UTF-8, a stock console is cp1252.
chcp 65001 >nul 2>&1
setlocal
title {APP_NAME} v{VERSION}

REM Always run from the folder holding this script, whatever the caller's cwd.
cd /d "%~dp0"

echo ============================================================
echo  {APP_NAME}  v{VERSION}
echo ============================================================
echo  Folder : %CD%
echo.
echo  Settings: per config.json (ships as hours=24, regions us-east-1 + ap-southeast-1)
echo  Credentials: EVAL_AWS_ACCESS_KEY_ID / EVAL_AWS_SECRET_ACCESS_KEY env vars
echo  (never stored in config.json).
echo.
REM %~dp0 in front of the exe: a bare name dies with 9009 on hardened images
REM where NoDefaultCurrentDirectoryInExePath excludes the current directory.
if not exist "%~dp0{EXE_NAME}" (
    echo ERROR: {EXE_NAME} not found next to this script.
    echo Unzip the whole release folder and keep the files together.
    echo.
    pause
    exit /b 1
)

echo Starting {EXE_NAME} ...
echo ------------------------------------------------------------
"%~dp0{EXE_NAME}" %*
set "RC=%ERRORLEVEL%"
echo ------------------------------------------------------------
if not "%RC%"=="0" (
    echo {APP_NAME} exited with code %RC%.
    echo See DEPLOY_README.md for troubleshooting.
    pause
    exit /b %RC%
)
echo {APP_NAME} stopped.
endlocal
"""

DEPLOY_README = """# Bedrock Cost Checker v__VERSION__

Quickly assess what your AWS Bedrock Claude usage is costing you. Portable -
no Python, no installer, no admin rights. Read-only: the app only ever reads
CloudWatch metrics and Cost Explorer data; it cannot change anything in your
AWS account.

## 1. Unzip

Unzip the WHOLE folder somewhere writable, e.g. `C:\\tools\\bedrock_checker`.
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
"""


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def check_versions() -> None:
    """The manifest names the zip; the exe prints its own version. Both must
    agree BEFORE the build, or we ship a binary announcing the wrong version."""
    init = (ROOT / "bedrock_checker" / "__init__.py").read_text(encoding="utf-8")
    m = re.search(r'__version__\s*=\s*"([^"]+)"', init)
    src_version = m.group(1) if m else None
    run_exe = (ROOT / "run_exe.py").read_text(encoding="utf-8")
    m2 = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', run_exe)
    exe_version = m2.group(1) if m2 else None
    if not (src_version == exe_version == VERSION):
        raise SystemExit(
            f"VERSION MISMATCH: __init__.py={src_version} run_exe.py={exe_version} "
            f"build_module={VERSION}. Fix all three to agree before building.")
    print(f"[ok] version agreement: {VERSION}")


def run_build() -> None:
    print("[..] build_exe.bat")
    proc = subprocess.run([str(ROOT / "build_exe.bat")], cwd=str(ROOT),
                          shell=True, check=False)
    if proc.returncode != 0:
        raise SystemExit(f"build_exe.bat failed with code {proc.returncode}")


def assemble() -> Path:
    dist = ROOT / "dist" / APP_NAME
    if not (dist / EXE_NAME).is_file():
        raise SystemExit(f"missing build artifact: {dist / EXE_NAME}")
    release = ROOT / "release" / f"{APP_NAME}_v{VERSION}"

    # keep_existing: preserve an operator-edited config.json across rebuilds.
    saved_config = None
    if (release / "config.json").is_file():
        saved_config = (release / "config.json").read_bytes()
    if release.exists():
        shutil.rmtree(release)
    shutil.copytree(dist, release)

    (release / "logs").mkdir(exist_ok=True)
    (release / "exports").mkdir(exist_ok=True)
    if saved_config is not None:
        (release / "config.json").write_bytes(saved_config)
        print("[ok] preserved existing config.json (keep_existing)")
    else:
        shutil.copy2(ROOT / "config.example.json", release / "config.json")

    (release / f"run_{APP_NAME.replace('_wins', '')}.bat").write_text(
        RUN_BAT.format(APP_NAME=APP_NAME, VERSION=VERSION, EXE_NAME=EXE_NAME),
        encoding="utf-8")
    (release / "DEPLOY_README.md").write_text(
        DEPLOY_README.replace("__VERSION__", VERSION), encoding="utf-8")

    files = []
    for path in sorted(p for p in release.rglob("*") if p.is_file()):
        files.append({"path": path.relative_to(release).as_posix(),
                      "size": path.stat().st_size,
                      "sha256": sha256_of(path)})
    manifest = {
        "schema": "portable-exe/release-manifest/1",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "app": {"name": APP_NAME, "version": VERSION, "exe": EXE_NAME},
        "verify": {"selftest_arg": "--selftest", "port_probe": None,
                   "port_probe_reason": "GUI client binds no port"},
        "files": files,
        "totals": {"files": len(files), "bytes": sum(f["size"] for f in files)},
    }
    (release / "RELEASE_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"[ok] assembled {release} ({len(files)} files)")
    return release


def make_zip(release: Path) -> Path:
    stamp = time.strftime("%Y%m%d")
    zip_path = release.parent / f"{release.name}_{stamp}.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(release.rglob("*")):
            if path.is_file():
                # arcname includes the folder: unzipping cannot scatter files.
                zf.write(path, path.relative_to(release.parent).as_posix())
    print(f"[ok] {zip_path} ({zip_path.stat().st_size / 1e6:.1f} MB)")
    return zip_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-build", action="store_true",
                        help="reuse an existing dist/ (assemble + zip only)")
    args = parser.parse_args()
    check_versions()
    if not args.skip_build:
        run_build()
    release = assemble()
    make_zip(release)
    print()
    print("next: python verify_release.py "
          f"release\\{release.name} --require-tk --skip-port-probe "
          f"--zip release\\{release.name}_{time.strftime('%Y%m%d')}.zip")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
