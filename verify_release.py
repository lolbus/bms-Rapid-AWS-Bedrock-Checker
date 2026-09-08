#!/usr/bin/env python
"""Release checklist for a portable Windows exe folder. Stdlib only.

Standalone counterpart to `dxcpack verify`: run it on an assembled release
folder to answer the one question a unit test cannot, which is whether the
*binary* works on a machine that has no Python.

    python verify_release.py release\\myapp_v1.2.0 --write-manifest
    python verify_release.py release\\myapp_v1.2.0 --zip release\\myapp_v1.2.0_20260902.zip

With no flags it reads RELEASE_MANIFEST.json for the app's name, version, exe
and verify settings; flags override. `--write-manifest` generates that file
first (sizes + sha256 of every file) and then verifies.

Exit code 0 = every check passed or was legitimately skipped, 1 = a failure.

Why each check exists is documented in SKILL.md section 7; the pitfalls each one
was written in response to are in section 8.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

MANIFEST_NAME = "RELEASE_MANIFEST.json"
SCHEMA = "portable-exe/release-manifest/1"

#: Never belongs in a transfer zip. Entry *names* are matched, case-insensitively.
DEV_ARTEFACTS = (".venv/", "venv/", "__pycache__/", ".git/", ".pytest_cache/",
                 ".mypy_cache/", ".ruff_cache/", "node_modules/", ".idea/", ".vscode/")
DEV_SUFFIXES = (".pyc", ".pyo", ".spec", ".pdb")


# --------------------------------------------------------------------------- #
# result plumbing
# --------------------------------------------------------------------------- #
@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""
    skipped: bool = False

    def line(self) -> str:
        tag = "SKIP" if self.skipped else ("PASS" if self.ok else "FAIL")
        return f"[{tag}] {self.name}" + (f" -- {self.detail}" if self.detail else "")


class Report:
    def __init__(self) -> None:
        self.checks: list[Check] = []

    def add(self, check: Check) -> Check:
        self.checks.append(check)
        print(check.line(), flush=True)
        return check

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if not c.ok and not c.skipped]

    @property
    def ok(self) -> bool:
        return not self.failures


def human(n: float) -> str:
    for unit in ("B", "KiB", "MiB", "GiB"):
        if n < 1024 or unit == "GiB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.1f} GiB"     # pragma: no cover


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


# --------------------------------------------------------------------------- #
# the clean-machine simulation
# --------------------------------------------------------------------------- #
def scrubbed_env(sandbox: Path, base: dict[str, str] | None = None) -> dict[str, str]:
    """An environment with no Python and no developer identity.

    The point of a portable exe is that it runs where Python does not, and a
    build machine's PATH hides every missing hidden import. So: PATH rebuilt
    from OS directories only, with any directory containing a python launcher
    dropped; PYTHONPATH / PYTHONHOME / VIRTUAL_ENV removed, since an inherited
    one would let the exe import from the dev tree; and HOME / TEMP / APPDATA
    pointed at a throwaway folder, so an app that writes user state cannot find
    a previous run's files and pass by accident.
    """
    src = dict(os.environ if base is None else base)
    keep = ("SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT",
            "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE", "OS",
            "COMPUTERNAME", "USERNAME", "PROGRAMFILES", "PROGRAMFILES(X86)",
            "PROGRAMDATA", "COMMONPROGRAMFILES", "PUBLIC")
    env = {k: v for k, v in src.items() if k.upper() in keep}

    root = src.get("SystemRoot") or src.get("SYSTEMROOT") or r"C:\Windows"
    candidates = [Path(root) / "system32", Path(root), Path(root) / "System32" / "Wbem",
                  Path(root) / "System32" / "WindowsPowerShell" / "v1.0"]
    path_dirs = []
    for directory in candidates:
        if not directory.exists():
            continue
        # Not belt and braces: the python.org installer puts py.exe / pyw.exe in
        # C:\Windows itself, which is one of the OS directories this list keeps.
        # Without this test the scrub leaves the Python launcher reachable and
        # the "no Python on PATH" claim is simply false.
        if any((directory / exe).exists() for exe in
               ("python.exe", "python3.exe", "pythonw.exe", "py.exe", "pyw.exe")):
            continue
        path_dirs.append(str(directory))
    env["PATH"] = os.pathsep.join(path_dirs)

    sandbox = Path(sandbox)
    for name in ("home", "temp", "appdata", "localappdata"):
        (sandbox / name).mkdir(parents=True, exist_ok=True)
    env["USERPROFILE"] = env["HOME"] = str(sandbox / "home")
    env["TEMP"] = env["TMP"] = str(sandbox / "temp")
    env["APPDATA"] = str(sandbox / "appdata")
    env["LOCALAPPDATA"] = str(sandbox / "localappdata")
    # A crash-hold input() blocks forever under a captured pipe, because
    # isatty() is true there (SKILL.md 8.4). The app must honour this.
    env["DXCPACK_NO_HOLD"] = "1"
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


# --------------------------------------------------------------------------- #
# RELEASE_MANIFEST.json
# --------------------------------------------------------------------------- #
def inventory(release: Path) -> list[dict[str, object]]:
    items = []
    for path in sorted(p for p in release.rglob("*") if p.is_file()):
        if path.name == MANIFEST_NAME:
            continue
        items.append({"path": path.relative_to(release).as_posix(),
                      "size": path.stat().st_size,
                      "sha256": sha256_of(path)})
    return items


def write_manifest(release: Path, app: dict[str, object],
                   verify: dict[str, object]) -> Path:
    files = inventory(release)
    doc = {
        "schema": SCHEMA,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "app": app,
        "verify": verify,
        "files": files,
        "totals": {"files": len(files), "bytes": sum(int(f["size"]) for f in files)},
    }
    target = release / MANIFEST_NAME
    # No BOM: this file is read by tools, and a BOM breaks a strict JSON parser.
    target.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return target


def read_manifest(release: Path) -> dict:
    path = release / MANIFEST_NAME
    if not path.is_file():
        return {}
    try:
        # utf-8-sig: tolerate a BOM someone's editor added (SKILL.md 8.3).
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}


def check_manifest_matches(release: Path) -> Check:
    doc = read_manifest(release)
    if not doc:
        return Check(f"{MANIFEST_NAME} matches the release contents", False,
                     f"missing or unreadable; run with --write-manifest")
    listed = {str(f["path"]): f for f in doc.get("files", [])}
    actual = {p.relative_to(release).as_posix(): p
              for p in release.rglob("*") if p.is_file() and p.name != MANIFEST_NAME}
    missing = sorted(set(listed) - set(actual))
    extra = sorted(set(actual) - set(listed))
    changed = [rel for rel, path in actual.items()
               if rel in listed and path.stat().st_size != listed[rel]["size"]]
    if missing or extra or changed:
        parts = []
        if missing:
            parts.append(f"{len(missing)} listed but absent (e.g. {missing[0]})")
        if extra:
            parts.append(f"{len(extra)} present but unlisted (e.g. {extra[0]})")
        if changed:
            parts.append(f"{len(changed)} changed size (e.g. {changed[0]})")
        return Check(f"{MANIFEST_NAME} matches the release contents", False,
                     "; ".join(parts))
    total = sum(int(f["size"]) for f in listed.values())
    return Check(f"{MANIFEST_NAME} matches the release contents", True,
                 f"{len(listed)} files, {human(total)}")


# --------------------------------------------------------------------------- #
# checks
# --------------------------------------------------------------------------- #
def check_exe(release: Path, exe_name: str) -> Check:
    exe = release / exe_name
    if not exe.is_file():
        siblings = ", ".join(sorted(p.name for p in release.glob("*.exe"))) or "none"
        return Check(f"{exe_name} present", False,
                     f"not found in {release}; .exe files here: {siblings}")
    size = exe.stat().st_size
    if size == 0:
        return Check(f"{exe_name} present", False, "the file is empty")
    return Check(f"{exe_name} present", True, human(size))


def snapshot(release: Path) -> dict[str, tuple[int, float] | None]:
    return {p.relative_to(release).as_posix():
            ((p.stat().st_size, p.stat().st_mtime) if p.is_file() else None)
            for p in release.rglob("*")}


def restore(release: Path, before: dict, backup: Path) -> list[str]:
    """Undo whatever booting the exe did inside the release folder.

    Verification runs the exe *in* the folder that is about to be zipped, so a
    server that creates data/ and logs/ on first boot, or rewrites config.json
    with its own resolved answers, corrupts the artifact it was meant to
    validate -- and the zip then ships one machine's state to every other
    machine (SKILL.md 8.1).
    """
    reverted = []
    after = snapshot(release)
    for rel in sorted(set(after) - set(before)):
        path = release / rel
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        elif path.exists():
            path.unlink()
        reverted.append(rel + ("/" if rel not in after or after[rel] is None else ""))
    for rel, meta in before.items():
        if meta is None:
            continue
        path = release / rel
        saved = backup / rel
        if not saved.is_file():
            continue
        if not path.is_file() or (path.stat().st_size, path.stat().st_mtime) != meta:
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(saved, path)
            if rel not in reverted:
                reverted.append(rel)
    return sorted(set(reverted))


def check_selftest(release: Path, exe_name: str, arg: str, *, expect: list[str],
                   require_tk: bool, timeout: float) -> Check:
    name = f"{exe_name} {arg} exits 0 under a scrubbed environment"
    with tempfile.TemporaryDirectory(prefix="verify_release_") as tmp:
        env = scrubbed_env(Path(tmp))
        try:
            proc = subprocess.run([str(release / exe_name), arg], cwd=str(release),
                                  env=env, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace",
                                  timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            return Check(name, False,
                         f"no exit after {timeout:.0f}s -- a selftest that hangs is "
                         f"usually a crash-hold input() that ignored DXCPACK_NO_HOLD")
        except OSError as exc:
            return Check(name, False, f"could not start: {exc}")
    output = (proc.stdout or "") + (proc.stderr or "")
    tail = " ".join(output.strip().splitlines()[-3:])[:400]
    if proc.returncode != 0:
        return Check(name, False, f"exit={proc.returncode}; tail: {tail}")
    wanted = list(expect) + (["tk: ok"] if require_tk else [])
    absent = [text for text in wanted if text not in output]
    if absent:
        return Check(name, False, f"exit=0 but output is missing {absent}; tail: {tail}")
    scrub_note = "PATH had no Python"
    return Check(name, True, f"exit=0; {scrub_note}; {len(output)} bytes output")


def check_port_probe(release: Path, exe_name: str, port: int, *, health: str,
                     ready_key: str | None, boot_timeout: float,
                     ready_timeout: float) -> Check:
    """Boot the exe, poll health until ready, then kill it.

    Readiness is polled from the *body*, not the status: a server that binds its
    port before loading a large payload answers 200 long before it can serve,
    and a status-only probe passes against a deployment whose payload never
    loaded.
    """
    name = f"{exe_name} serves {health} on port {port} then shuts down"
    url = f"http://127.0.0.1:{port}{health}"
    with tempfile.TemporaryDirectory(prefix="verify_probe_") as tmp:
        env = scrubbed_env(Path(tmp))
        creation = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        try:
            proc = subprocess.Popen([str(release / exe_name)], cwd=str(release), env=env,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    creationflags=creation)
        except OSError as exc:
            return Check(name, False, f"could not start: {exc}")
        started = time.monotonic()
        try:
            body = None
            deadline = started + boot_timeout + ready_timeout
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    return Check(name, False,
                                 f"exited early with code {proc.returncode} after "
                                 f"{time.monotonic() - started:.1f}s")
                try:
                    with urllib.request.urlopen(url, timeout=5) as response:
                        status = response.status
                        raw = response.read().decode("utf-8", "replace")
                except (urllib.error.URLError, OSError, TimeoutError):
                    time.sleep(0.5)
                    continue
                if status != 200:
                    time.sleep(0.5)
                    continue
                if not ready_key:
                    return Check(name, True,
                                 f"GET {health} -> 200 in {time.monotonic() - started:.1f}s")
                try:
                    body = json.loads(raw)
                except ValueError:
                    return Check(name, False,
                                 f"{health} answered 200 but the body is not JSON, so "
                                 f"{ready_key!r} cannot be read: {raw[:120]!r}")
                if body.get(ready_key):
                    return Check(name, True,
                                 f"GET {health} -> 200 with {ready_key}=true in "
                                 f"{time.monotonic() - started:.1f}s")
                time.sleep(1.0)
            waited = time.monotonic() - started
            if body is None:
                return Check(name, False, f"no 200 from {health} within {waited:.0f}s")
            return Check(name, False,
                         f"{health} answered 200 but {ready_key!r} stayed false for "
                         f"{waited:.0f}s -- the service is up and its payload never loaded")
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=30)


def check_zip(zip_path: Path) -> Check:
    name = f"{zip_path.name} contains no absolute paths or dev artefacts"
    if not zip_path.is_file():
        return Check(name, False, f"not found: {zip_path}")
    problems: list[str] = []
    try:
        with zipfile.ZipFile(zip_path) as archive:
            entries = archive.infolist()
            names = [info.filename for info in entries]
            unpacked = sum(info.file_size for info in entries)
    except zipfile.BadZipFile as exc:
        return Check(name, False, f"unreadable: {exc}")
    if not names:
        return Check(name, False, "the archive is empty")
    for entry in names:
        low = entry.lower().replace("\\", "/")
        if low.startswith("/") or (len(low) > 1 and low[1] == ":"):
            problems.append(f"absolute path: {entry}")
        if ".." in low.split("/"):
            problems.append(f"escapes the extraction root: {entry}")
        if any(bad in low for bad in DEV_ARTEFACTS):
            problems.append(f"dev artefact: {entry}")
        if low.endswith(DEV_SUFFIXES):
            problems.append(f"dev artefact: {entry}")
    roots = {entry.replace("\\", "/").split("/", 1)[0] for entry in names}
    if len(roots) != 1:
        problems.append(f"unzips to {len(roots)} top-level entries {sorted(roots)[:4]} -- "
                        f"zip the release *folder*, not its contents, or an operator's "
                        f"Downloads gets scattered")
    if problems:
        shown = "; ".join(sorted(set(problems))[:4])
        return Check(name, False, f"{len(set(problems))} problem(s): {shown}")
    return Check(name, True, f"{len(names)} entries, unzips to {human(unpacked)}")


# --------------------------------------------------------------------------- #
# orchestration
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Release checklist for a portable Windows exe folder.")
    parser.add_argument("release", type=Path, help="the assembled release folder")
    parser.add_argument("--zip", type=Path, default=None, help="also audit this zip")
    parser.add_argument("--name", default=None, help="app name (default: from manifest)")
    parser.add_argument("--version", default=None, help="expected version")
    parser.add_argument("--exe", default=None, help="exe file name")
    # Must be given with an '=': a value that itself starts with '-' is
    # otherwise parsed as the next option.
    parser.add_argument("--selftest-arg", default=None,
                        help="selftest flag; write it as --selftest-arg=--selftest "
                             "(default: read from the release manifest)")
    parser.add_argument("--selftest-timeout", type=float, default=180.0)
    parser.add_argument("--require-tk", action="store_true",
                        help="GUI app: the selftest must print 'tk: ok'")
    parser.add_argument("--port", type=int, default=None, help="port probe")
    parser.add_argument("--health", default="/health")
    parser.add_argument("--ready-key", default=None,
                        help="JSON key in the health body that means 'ready'")
    parser.add_argument("--boot-timeout", type=float, default=120.0)
    parser.add_argument("--ready-timeout", type=float, default=240.0)
    parser.add_argument("--skip-port-probe", action="store_true")
    parser.add_argument("--skip-selftest", action="store_true")
    parser.add_argument("--write-manifest", action="store_true",
                        help=f"generate {MANIFEST_NAME} before verifying")
    args = parser.parse_args(argv)

    release: Path = args.release.resolve()
    if not release.is_dir():
        print(f"not a directory: {release}", file=sys.stderr)
        return 2

    doc = read_manifest(release)
    app = dict(doc.get("app") or {})
    verify = dict(doc.get("verify") or {})
    name = args.name or str(app.get("name") or release.name.split("_v")[0])
    version = args.version or str(app.get("version") or "")
    exe_name = args.exe or str(app.get("exe") or f"{name}.exe")
    selftest_arg = args.selftest_arg or verify.get("selftest_arg")
    port = args.port if args.port is not None else verify.get("port_probe")
    health = args.health if args.health != "/health" else verify.get("health_path", "/health")
    ready_key = args.ready_key or verify.get("ready_json_key")
    # A build that deliberately omitted a payload the probe needs records that
    # here, so an unsatisfiable probe is a SKIP with a reason rather than a
    # multi-minute timeout that reads like a broken build.
    needs = list(verify.get("port_probe_needs") or [])
    skipped_dirs = list((doc.get("build") or {}).get("skipped_dirs") or [])
    unmet = [d for d in needs if d in skipped_dirs]

    if args.write_manifest:
        write_manifest(release,
                       app={"name": name, "version": version, "exe": exe_name},
                       verify={"selftest_arg": selftest_arg, "port_probe": port,
                               "health_path": health, "ready_json_key": ready_key,
                               "port_probe_needs": needs})
        print(f"==> wrote {release / MANIFEST_NAME}", flush=True)

    report = Report()
    report.add(check_exe(release, exe_name))
    report.add(check_manifest_matches(release))

    run_probe = bool(port) and not args.skip_port_probe and not unmet
    will_boot = (not args.skip_selftest and bool(selftest_arg)) or run_probe

    backup: Path | None = None
    before: dict = {}
    if will_boot and report.ok:
        # Snapshot before anything boots, so the folder can be handed back exactly
        # as it was built.
        before = snapshot(release)
        backup = Path(tempfile.mkdtemp(prefix="verify_backup_"))
        for rel, meta in before.items():
            if meta is None:
                continue
            target = backup / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(release / rel, target)

    try:
        if args.skip_selftest or not selftest_arg:
            report.add(Check("selftest", True, "no selftest argument configured",
                             skipped=True))
        elif report.failures:
            report.add(Check("selftest", True, "skipped: the exe is not usable",
                             skipped=True))
        else:
            # The banner expectation is "<name> v<version>", never the bare
            # "v<version>": every onedir release lives in a folder called
            # <name>_v<version>, which a selftest that prints its own app_dir
            # emits verbatim -- so a bare-substring check is satisfied by the
            # *folder name* whatever the binary announces, and passes a zip whose
            # exe is a version behind.
            expect = [f"{name} v{version}"] if version else []
            report.add(check_selftest(release, exe_name, selftest_arg, expect=expect,
                                      require_tk=args.require_tk,
                                      timeout=args.selftest_timeout))

        if run_probe and not report.failures:
            report.add(check_port_probe(release, exe_name, int(port), health=health,
                                       ready_key=ready_key,
                                       boot_timeout=args.boot_timeout,
                                       ready_timeout=args.ready_timeout))
        elif unmet and not args.skip_port_probe:
            report.add(Check("port probe", True,
                             f"SKIP: this build did not bundle {', '.join(unmet)}, which "
                             f"port_probe_needs declares the probe requires. Booting it "
                             f"would time out waiting for a payload the build "
                             f"deliberately left out.", skipped=True))
        elif port:
            report.add(Check("port probe", True, "skipped on request", skipped=True))
        else:
            report.add(Check("port probe", True, "no port configured", skipped=True))
    finally:
        if backup is not None:
            reverted = restore(release, before, backup)
            shutil.rmtree(backup, ignore_errors=True)
            report.add(Check("release folder handed back exactly as it was built", True,
                             f"reverted {len(reverted)} path(s): {', '.join(reverted[:6])}"
                             if reverted else "the boot left nothing behind"))

    if args.zip is not None:
        report.add(check_zip(args.zip.resolve()))

    print()
    print(f"release folder : {release}")
    if args.zip is not None and args.zip.is_file():
        print(f"transfer zip   : {args.zip.resolve()} ({human(args.zip.stat().st_size)})")
        print(f"sha256         : {sha256_of(args.zip.resolve())}")
    print(f"verification   : {'PASSED' if report.ok else 'FAILED'}")
    for failure in report.failures:
        print("  " + failure.line())
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
