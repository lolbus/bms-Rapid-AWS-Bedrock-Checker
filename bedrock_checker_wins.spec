# -*- mode: python ; coding: utf-8 -*-
# bedrock_checker_wins.spec -- rendered from the portable-exe-packing skill's
# app.spec.tmpl: common section + ONEDIR tail only (a spec with both tails
# defines exe twice). onedir chosen because botocore ships ~100 MB of service
# JSON; onefile would re-extract it to %TEMP% on every launch.

import sys
from pathlib import Path

# SPECPATH is the directory holding this spec == the app's uv project root.
project_dir = Path(SPECPATH)

# --- venv site-packages discovery -------------------------------------------
# PyInstaller must analyse the app project's own locked environment, not the
# ambient interpreter's.
site_packages = None
venv_dir = project_dir / '.venv'
if venv_dir.exists():
    win_site = venv_dir / 'Lib' / 'site-packages'
    if win_site.exists():
        site_packages = win_site
    else:
        lib_dir = venv_dir / 'lib'
        if lib_dir.exists():
            for p in sorted(lib_dir.iterdir()):
                if p.name.startswith('python') and (p / 'site-packages').exists():
                    site_packages = p / 'site-packages'
                    break

pathex_list = [str(project_dir)]
if site_packages is not None:
    pathex_list.insert(0, str(site_packages))
    sys.path.insert(0, str(site_packages))
    print('[ok] venv site-packages: %s' % site_packages)
else:
    print('[warn] no .venv beside the spec; analysing with the ambient interpreter')

sys.path.insert(0, str(project_dir))

entry_script = str(project_dir / 'run_exe.py')

from PyInstaller.utils.hooks import collect_all, collect_submodules

# run_exe.py reaches the app through importlib.import_module(APP_IMPORT) -- a
# string -- so the graph never sees it. The app's own modules MUST be listed
# here or the build succeeds and the exe dies with ModuleNotFoundError.
all_hiddenimports = [
    'bedrock_checker', 'bedrock_checker.app', 'bedrock_checker.config',
    'bedrock_checker.pricing', 'bedrock_checker.creds', 'bedrock_checker.theme',
    'bedrock_checker.widgets',
    'bedrock_checker.methods', 'bedrock_checker.methods.cloudwatch',
    'bedrock_checker.methods.cost_explorer', 'bedrock_checker.methods.calibrated',
    'bedrock_checker.methods.discovery',
    'bedrock_checker.tabs', 'bedrock_checker.tabs.base',
    'bedrock_checker.tabs.tab_cloudwatch', 'bedrock_checker.tabs.tab_cost_explorer',
    'bedrock_checker.tabs.tab_calibrated', 'bedrock_checker.tabs.tab_discovery',
    'bedrock_checker.tabs.tab_settings',
    'tkinter', 'tkinter.ttk', 'tkinter.font', 'tkinter.scrolledtext',
    'tkinter.messagebox', 'tkinter.filedialog',
]

all_datas = []
all_binaries = []

# collect_all() per fragile package. botocore carries its service JSON in
# data/ -- without this, boto3.client('cloudwatch') raises UnknownServiceError
# in the exe only.
packages_to_collect = ['boto3', 'botocore', 'dateutil', 'jmespath', 'urllib3',
                       'certifi']

for package in packages_to_collect:
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
        all_datas.extend(pkg_datas)
        all_binaries.extend(pkg_binaries)
        all_hiddenimports.extend(pkg_hidden)
        print('[ok] collected: %s' % package)
    except Exception as exc:
        print('[warn] collect_all(%s) failed: %s' % (package, exc))
        try:
            subs = collect_submodules(package)
            all_hiddenimports.extend(subs)
            print('     fallback: %d submodules' % len(subs))
        except Exception:
            pass

# Brand asset for the header wordmark (loaded via sys._MEIPASS at runtime).
assets_dir = project_dir / 'bedrock_checker' / 'assets'
if assets_dir.exists():
    all_datas.append((str(assets_dir), 'bedrock_checker/assets'))
    print('[ok] bundled assets: %s' % assets_dir)

all_hiddenimports = sorted(set(all_hiddenimports))
print('[ok] hidden imports: %d' % len(all_hiddenimports))

a = Analysis(
    [entry_script],
    pathex=pathex_list,
    binaries=all_binaries,
    datas=all_datas,
    hiddenimports=all_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'pandas', 'numpy', 'scipy', 'torch', 'tensorflow',
              'keras', 'PIL', 'cv2', 'IPython', 'jupyter', 'notebook',
              'pytest', '_pytest', 'setuptools', 'pkg_resources',
              'lib2to3', 'pydoc_data', 'test', 'sqlite3'],
    noarchive=False,
)

pyz = PYZ(a.pure)

# onedir: exe + _internal/ beside it. No %TEMP% re-extraction per launch.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='bedrock_checker_wins',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='bedrock_checker_wins',
)
