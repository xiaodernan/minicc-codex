#Requires -Version 5.1
<#
.SYNOPSIS
    Build the installable artifacts (wheel + sdist) for minicc into dist/.

.DESCRIPTION
    The workbench (web/) and the VSCode companion (ide/) live at the repo root
    but must ship inside the minicc package, otherwise an installed
    `minicc-web` serves a 404 workbench. setup.py performs that copy, and this
    script verifies the payload actually landed before declaring success.

.PARAMETER Python
    Interpreter used to run the PEP 517 backend. Defaults to `python` on PATH.

.PARAMETER OutDir
    Artifact directory. Defaults to `dist`.

.PARAMETER SkipWebBuild
    Do not run `npm run build:web` first (use the bundles already on disk).

.PARAMETER Clean
    Remove the artifact directory before building.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts/build-dist.ps1
#>
param(
    [string]$Python = "",
    [string]$OutDir = "dist",
    [switch]$SkipWebBuild,
    [switch]$Clean
)

$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo
if (-not $Python) { $Python = "python" }

function Invoke-Python([string]$Code, [string[]]$Arguments) {
    & $Python -c $Code @Arguments
    if ($LASTEXITCODE -ne 0) { throw "python exited with $LASTEXITCODE" }
}

Write-Host "[build-dist] repo: $repo"

if ($Clean -and (Test-Path $OutDir)) {
    Write-Host "[build-dist] removing $OutDir"
    Remove-Item -Recurse -Force $OutDir
}

if (-not $SkipWebBuild) {
    $npm = Get-Command npm -ErrorAction SilentlyContinue
    if ($npm -and (Test-Path (Join-Path $repo "node_modules/esbuild"))) {
        Write-Host "[build-dist] npm run build:web"
        npm run build:web
        if ($LASTEXITCODE -ne 0) { throw "npm run build:web failed" }
    }
    else {
        Write-Warning "npm or esbuild unavailable - packaging the bundles already on disk"
    }
}

# The backend must be importable in this interpreter: `pip wheel` without
# --no-build-isolation provisions its own environment, but a local build does not.
Invoke-Python @'
import importlib.util
import setuptools
have = tuple(int(part) for part in setuptools.__version__.split('.')[:2] if part.isdigit())
can_build = bool(
    importlib.util.find_spec('setuptools.command.bdist_wheel')  # vendored since 70.1
    or importlib.util.find_spec('wheel.bdist_wheel')            # older: separate wheel pkg
)
if not can_build:
    raise SystemExit('no wheel backend: run pip install -U setuptools')
if have < (70, 1) and not importlib.util.find_spec('wheel.bdist_wheel'):
    raise SystemExit('setuptools %s is too old; run pip install -U setuptools' % setuptools.__version__)
print('[build-dist] backend: setuptools %s' % setuptools.__version__)
'@ @()

Invoke-Python @'
import pathlib
import sys
from setuptools import build_meta

out = pathlib.Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
wheel = build_meta.build_wheel(str(out))
sdist = build_meta.build_sdist(str(out))
print(wheel)
print(sdist)
'@ @($OutDir)

# Fail the build if the workbench payload is missing: an install that cannot
# serve index.html is worse than no install at all.
Invoke-Python @'
import json
import pathlib
import sys
import zipfile

out = pathlib.Path(sys.argv[1])
wheel = max(out.glob('*.whl'), key=lambda p: p.stat().st_mtime)
names = set(zipfile.ZipFile(wheel).namelist())
required = [
    'minicc/__init__.py',
    'minicc/web_static/index.html',
    'minicc/web_static/asset-manifest.json',
    'minicc/ide_static/vscode/extension.js',
]
missing = [name for name in required if name not in names]
manifest = json.loads((pathlib.Path.cwd() / 'web' / 'asset-manifest.json').read_text(encoding='utf-8'))
for versioned in manifest.values():
    bundled = 'minicc/web_static' + str(versioned)
    if bundled not in names:
        missing.append(bundled)
for junk in sorted(n for n in names if '.env' in n or 'node_modules' in n or '__pycache__' in n):
    missing.append('junk:' + junk)
if missing:
    raise SystemExit('%s is missing payload: %s' % (wheel.name, ', '.join(missing)))
print('[build-dist] %s carries %d files (workbench + IDE assets verified)' % (wheel.name, len(names)))
'@ @($OutDir)

Get-ChildItem $OutDir | Where-Object { $_.Name -match "\.(whl|tar\.gz)$" } | ForEach-Object {
    $sizeKb = [math]::Round($_.Length / 1KB, 1)
    Write-Host ("[build-dist] artifact: {0}  {1} KB  sha256:{2}" -f $_.Name, $sizeKb, (Get-FileHash $_.FullName -Algorithm SHA256).Hash.Substring(0, 16))
}
Write-Host "[build-dist] done"
