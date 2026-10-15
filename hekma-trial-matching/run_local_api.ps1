# TrialGPT local API — always uses .venv Python 3.10 (not system Python 3.14)
param(
    [int]$Port = 8000
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Get-DotEnvValue {
    param([string]$Name)
    $value = ""
    foreach ($line in Get-Content ".env" -Encoding UTF8) {
        if ($line -match '^\s*#' -or $line -notmatch '=') { continue }
        $key, $rest = $line -split '=', 2
        if ($key.Trim() -eq $Name) {
            $value = $rest.Trim()
        }
    }
    return $value
}

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "Creating Python 3.10 venv..."
    py -3.10 -m venv .venv
    & $venvPython -m pip install --upgrade pip
    & $venvPython -m pip install -r requirements.txt
    & $venvPython -m pip install qdrant-client pypdf "fastembed>=0.7.0" rank_bm25
    # NLTK tokenizer data required by the T2P matching stage.
    & $venvPython -c "import nltk; nltk.download('punkt_tab'); nltk.download('punkt')"
}

Write-Host "Using: $(& $venvPython --version)"
Write-Host "Python path: $venvPython"

if (-not (Test-Path ".env")) {
    Write-Host "ERROR: .env missing. Run: py -3.10 scripts\setup_local.py"
    exit 1
}

$openaiKey = Get-DotEnvValue "OPENAI_API_KEY"
$anthropicKey = Get-DotEnvValue "ANTHROPIC_API_KEY"

if (-not $openaiKey) {
    Write-Host "ERROR: OPENAI_API_KEY is empty in .env"
    exit 1
}
if (-not $anthropicKey) {
    Write-Host "ERROR: ANTHROPIC_API_KEY is empty in .env (required for Claude P2T/T2P)"
    exit 1
}

Write-Host ""
Write-Host "Starting TrialGPT API at http://127.0.0.1:$Port"
Write-Host "Health: http://127.0.0.1:$Port/health"
Write-Host ""

& $venvPython -m uvicorn main:app --reload --host 127.0.0.1 --port $Port
