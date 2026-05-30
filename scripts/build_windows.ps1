param(
    [string]$Version = '',

    [ValidateSet('Optimal', 'Fastest', 'NoCompression')]
    [string]$ZipCompressionLevel = 'Optimal',

    [switch]$SkipTests,

    [switch]$SkipSelfTest
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if (Get-Variable PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $true
}

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$BuildRoot = Join-Path $Root '.build\windows'
$Venv = Join-Path $BuildRoot '.venv'
$DistRoot = Join-Path $BuildRoot 'dist'
$WorkRoot = Join-Path $BuildRoot 'pyinstaller'
$BundledModelsRoot = Join-Path $BuildRoot 'bundled-models'
$ReleaseRoot = Join-Path $Root 'dist'
$AppDir = Join-Path $DistRoot 'NTE Dice Analysis'
$Exe = Join-Path $AppDir 'NTE Dice Analysis.exe'

function Remove-WorkspacePath {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }

    $resolvedPath = (Resolve-Path -LiteralPath $Path).Path
    $resolvedRoot = (Resolve-Path -LiteralPath $Root).Path
    if (-not $resolvedPath.StartsWith($resolvedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove path outside workspace: $resolvedPath"
    }

    Remove-Item -LiteralPath $resolvedPath -Recurse -Force
}

if ($env:PROCESSOR_ARCHITECTURE -notin @('AMD64', 'x86_64')) {
    throw 'Windows packaging currently supports x64 only.'
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw 'uv is required to build the Windows portable package.'
}

Set-Location $Root

Remove-WorkspacePath $BuildRoot
New-Item -ItemType Directory -Path $BuildRoot, $ReleaseRoot -Force | Out-Null

$env:UV_PROJECT_ENVIRONMENT = $Venv
$env:DISABLE_MODEL_SOURCE_CHECK = 'True'
$env:PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK = 'True'
uv sync --locked
$Python = Join-Path $Venv 'Scripts\python.exe'

if (-not $Version) {
    $Version = & $Python -c "import tomllib; print(tomllib.load(open('pyproject.toml', 'rb'))['project']['version'])"
}

if (-not $SkipTests) {
    & $Python -m pytest
}

$PyInstaller = Join-Path $Venv 'Scripts\pyinstaller.exe'

& $Python (Join-Path $Root 'scripts\bundle_ocr_models.py') $BundledModelsRoot

$env:NTE_DICE_ANALYSIS_BUNDLED_MODELS = $BundledModelsRoot
try {
    & $PyInstaller `
        --noconfirm `
        --clean `
        --distpath $DistRoot `
        --workpath $WorkRoot `
        (Join-Path $Root 'packaging\windows\nte_dice_analysis.spec')
}
finally {
    Remove-Item Env:\NTE_DICE_ANALYSIS_BUNDLED_MODELS -ErrorAction SilentlyContinue
}

Copy-Item `
    -LiteralPath (Join-Path $Root 'packaging\windows\README.windows.txt') `
    -Destination (Join-Path $AppDir 'README.windows.txt') `
    -Force

if (-not $SkipSelfTest) {
    $SelfTest = Start-Process -FilePath $Exe -ArgumentList '--self-test' -Wait -PassThru
    if ($SelfTest.ExitCode -ne 0) {
        throw "Packaged self-test failed with exit code $($SelfTest.ExitCode)."
    }
}

$ZipName = "NTE-Dice-Analysis-windows-x64-v$Version.zip"
$ZipPath = Join-Path $ReleaseRoot $ZipName
$CompressionLevel = [System.IO.Compression.CompressionLevel]::$ZipCompressionLevel
Add-Type -AssemblyName System.IO.Compression.FileSystem

Write-Host "Creating $ZipName with $ZipCompressionLevel compression..."
$ArchiveStopwatch = [System.Diagnostics.Stopwatch]::StartNew()
$Compressed = $false
for ($Attempt = 1; $Attempt -le 5; $Attempt++) {
    if (Test-Path -LiteralPath $ZipPath) {
        Remove-Item -LiteralPath $ZipPath -Force
    }

    try {
        [System.IO.Compression.ZipFile]::CreateFromDirectory(
            $AppDir,
            $ZipPath,
            $CompressionLevel,
            $false
        )
        $Compressed = $true
        break
    }
    catch {
        if ($Attempt -eq 5) {
            throw
        }
        Start-Sleep -Seconds 2
    }
}

if (-not $Compressed) {
    throw 'Failed to create ZIP archive.'
}

$ArchiveStopwatch.Stop()
Write-Host "Wrote $ZipPath in $([math]::Round($ArchiveStopwatch.Elapsed.TotalSeconds, 1)) seconds"
