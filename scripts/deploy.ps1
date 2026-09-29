$ErrorActionPreference = "Stop"

foreach ($name in @(
        "SMARTSUITE_API_TOKEN",
        "RER_SESSION_AUTH_API_KEY_VALUE",
        "RER_SCRAPER_API_KEY_VALUE",
        "GMAIL_TOKEN_JSON"
    )) {
    if (-not (Get-Item "Env:$name" -ErrorAction SilentlyContinue).Value) {
        throw "$name must be loaded before deployment. Run .\.envrc.ps1 first."
    }
}

sam build
sam deploy --parameter-overrides `
    "SmartSuiteApiToken=$env:SMARTSUITE_API_TOKEN" `
    "GmailTokenJson=$env:GMAIL_TOKEN_JSON" `
    "SessionAuthApiKeyValue=$env:RER_SESSION_AUTH_API_KEY_VALUE" `
    "ScraperApiKeyValue=$env:RER_SCRAPER_API_KEY_VALUE"
