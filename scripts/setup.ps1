$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv is required. Install uv, reopen PowerShell, and rerun .\scripts\setup.ps1."
}

$node = Get-Command node -ErrorAction SilentlyContinue
if (-not $node) {
    throw "Node.js 20 or newer is required for Playwright MCP. Install Node.js and reopen PowerShell."
}
$nodeVersion = (& node --version) -replace '^v', ''
if ($nodeVersion -notmatch '^\d+' -or [int]($Matches[0]) -lt 20) {
    throw "Node.js 20 or newer is required; found $nodeVersion."
}

if (-not (Test-Path -LiteralPath ".env")) {
    Copy-Item -LiteralPath ".env.example" -Destination ".env"
    Write-Host "Created .env from .env.example."
} else {
    Write-Host "Keeping existing .env."
}

Write-Host "Installing locked Python dependencies..."
uv sync
if ($LASTEXITCODE -ne 0) {
    throw "uv sync failed with exit code $LASTEXITCODE."
}

Write-Host "Checking the package and LangGraph CLI..."
uv run python -c "import insightai.main; print('Main module import OK')"
if ($LASTEXITCODE -ne 0) {
    throw "The main module import check failed."
}
uv run langgraph --help | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "The LangGraph CLI check failed."
}

Write-Host "Setup complete. Before running, set OPENAI_API_KEY in .env. DATABASE_URL is optional and enables persistence."
Write-Host "Then start scripts/start-playwright-mcp.bat and, in another terminal, run: uv run langgraph dev"
