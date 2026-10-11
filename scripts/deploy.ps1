$ErrorActionPreference = "Stop"

foreach ($name in @(
        "SMARTSUITE_API_TOKEN",
        "RER_SESSION_AUTH_API_KEY_VALUE",
        "GMAIL_TOKEN_JSON"
    )) {
    if (-not (Get-Item "Env:$name" -ErrorAction SilentlyContinue).Value) {
        throw "$name must be loaded before deployment. Run .\.envrc.ps1 first."
    }
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$wheelDirectory = Join-Path $repoRoot "src\.sam-wheels"
New-Item -ItemType Directory -Force -Path $wheelDirectory | Out-Null
Get-ChildItem $wheelDirectory -Filter "smartsuite_python-*.whl" -ErrorAction SilentlyContinue |
Remove-Item -Force
python -m pip wheel --no-deps --wheel-dir $wheelDirectory `
    "smartsuite-python @ git+https://github.com/cbility/smartsuite-python.git@a61bf044278c997c60369ea714d355417fa56a37"
if ($LASTEXITCODE -ne 0) {
    throw "Failed to build the SmartSuite dependency wheel."
}

sam build
if ($LASTEXITCODE -ne 0) {
    throw "SAM build failed; deployment was not started."
}

sam deploy --parameter-overrides `
    "SmartSuiteApiToken=$env:SMARTSUITE_API_TOKEN" `
    "GmailTokenJson=$env:GMAIL_TOKEN_JSON" `
    "SessionAuthApiKeyValue=$env:RER_SESSION_AUTH_API_KEY_VALUE"
if ($LASTEXITCODE -ne 0) {
    throw "SAM deployment failed."
}
