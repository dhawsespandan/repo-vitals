# WP-8 launcher. Run it yourself, from PowerShell:
#     powershell -ExecutionPolicy Bypass -File D:\Symbiosis\RepoVitals\research_data\wp8_run_all.ps1
#
# Runs conditions A, B, C in order, never two at once (File B WP-8), on the team
# members' keys in backend\.env.team, one key at a time. When a member's Groq
# key stops answering (its daily cap), the next member's key continues the same
# condition with --resume. Keys added to .env.team while it runs are picked up.
# Every switch is written to research_data\logs\wp8_key_ledger.tsv (member
# names only, never keys) for wp8_run_log.md.

$root    = "D:\Symbiosis\RepoVitals"
$backend = "$root\backend"
$envTeam = "$backend\.env.team"
$runs    = "$root\research_data\runs"
$logs    = "$root\research_data\logs"
$ledger  = "$logs\wp8_key_ledger.tsv"
$py      = "$backend\.venv\Scripts\python.exe"
$suffix  = "_75246f3b_openai-gpt-oss-120b"

$env:DATABASE_URL     = "postgres://repovitals:repovitals@localhost:5433/repovitals_research"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUNBUFFERED = "1"

function Read-Keys([string]$prefix) {
    Get-Content $envTeam | ForEach-Object {
        if ($_ -match "^$prefix(\w+)=(.+)$") {
            [pscustomobject]@{ Member = $Matches[1]; Key = $Matches[2].Trim() }
        }
    }
}

function Get-Progress([string]$c) {
    $f = "$runs\$c$suffix\run.json"
    if (-not (Test-Path $f)) { return [pscustomobject]@{ Done = 0; Failed = 0 } }
    $j = Get-Content $f -Raw | ConvertFrom-Json
    [pscustomobject]@{ Done = [int]$j.completed + [int]$j.failed; Failed = [int]$j.failed }
}

function Write-Ledger([string]$text) {
    "$((Get-Date).ToUniversalTime().ToString('s'))Z`t$text" | Add-Content -Encoding utf8 $ledger
    Write-Host $text
}

function Invoke-Run([string]$c, $groq, $gemini, [string[]]$extra) {
    $env:GROQ_API_KEY   = $groq.Key
    $env:GEMINI_API_KEY = $gemini.Key
    $log = "$logs\wp8_$c.log"
    "=== START $((Get-Date).ToUniversalTime().ToString('s'))Z condition $c groq=$($groq.Member) gemini=$($gemini.Member) $extra" | Add-Content -Encoding utf8 $log
    & $py manage.py run_experiment --condition $c --items labelled_set.jsonl --resume @extra 2>&1 | ForEach-Object { "$_" } | Add-Content -Encoding utf8 $log
    "=== EXIT $LASTEXITCODE $((Get-Date).ToUniversalTime().ToString('s'))Z" | Add-Content -Encoding utf8 $log
}

# Judge anything the inline judge could not reach (Gemini's daily quota), one Gemini key at a time.
# Runs at the end, and also when generation stops for lack of Groq quota, so judging never waits on Groq.
function Invoke-Judging {
    $ids = @("A", "B", "C") | Where-Object { Test-Path "$runs\$_$suffix\items.jsonl" } | ForEach-Object { "$_$suffix" }
    foreach ($gemini in @(Read-Keys "GEMINI_KEY_")) {
        $env:GEMINI_API_KEY = $gemini.Key
        Write-Ledger "analyze --judge gemini=$($gemini.Member) runs=$($ids -join ',')"
        & $py manage.py analyze_experiment --runs @ids --judge 2>&1 | ForEach-Object { "$_" } | Add-Content -Encoding utf8 "$logs\wp8_analyze.log"
    }
}

Set-Location $backend
New-Item -ItemType Directory -Force $logs | Out-Null
$spent = @{}          # Groq members whose daily cap was reached in this session
$gemIndex = @{ A = 0; B = 1; C = 0 }   # A 150 + C 300 judge calls on one Gemini key, B 300 on the next
$stalls = 0

foreach ($c in "A", "B", "C") {
    while ((Get-Progress $c).Done -lt 150) {
        $groq = Read-Keys "GROQ_KEY_" | Where-Object { -not $spent.ContainsKey($_.Member) } | Select-Object -First 1
        if (-not $groq) {
            Write-Ledger "STOPPED at ${c} ($((Get-Progress $c).Done)/150): no unspent Groq key. Judging what exists, then exiting; add keys or wait, and run this script again."
            Invoke-Judging
            exit 1
        }
        $gems = @(Read-Keys "GEMINI_KEY_")
        $gemini = $gems[$gemIndex[$c] % $gems.Count]

        $before = (Get-Progress $c).Done
        Write-Ledger "start $c at $before/150 groq=$($groq.Member) gemini=$($gemini.Member)"
        Invoke-Run $c $groq $gemini @()
        $after = (Get-Progress $c).Done
        Write-Ledger "end   $c at $after/150 groq=$($groq.Member) (+$($after - $before))"

        if ($after -lt 150) { $spent[$groq.Member] = $true }
        if ($after -eq $before) { $stalls++ } else { $stalls = 0 }
        if ($stalls -ge 2) {
            Write-Ledger "STOPPED at ${c}: two keys in a row made no progress - not a daily cap. Read research_data\logs\wp8_$c.log."
            exit 2
        }
    }
    if ((Get-Progress $c).Failed -gt 0) {
        $groq = Read-Keys "GROQ_KEY_" | Where-Object { -not $spent.ContainsKey($_.Member) } | Select-Object -First 1
        if ($groq) {
            $gems = @(Read-Keys "GEMINI_KEY_")
            Write-Ledger "retry-failed $c ($((Get-Progress $c).Failed) failed) groq=$($groq.Member)"
            Invoke-Run $c $groq $gems[$gemIndex[$c] % $gems.Count] @("--retry-failed")
        }
    }
    Write-Ledger "DONE ${c}: $((Get-Progress $c).Done)/150, $((Get-Progress $c).Failed) failed"
}

Invoke-Judging
Write-Ledger "ALL DONE. Tables: research_data\runs\analysis\tables.md"
