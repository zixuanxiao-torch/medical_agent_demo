<#
.SYNOPSIS
  Run cloudflared tunnel connector for local FastAPI (enterprise WeChat callback via HTTPS).

.DESCRIPTION
  - Use -Token when Cloudflare Zero Trust shows: cloudflared tunnel run --token <TOKEN>
  - Use -TunnelName for a CLI-created tunnel (credentials in %USERPROFILE%\.cloudflared\)

  If QUIC times out on your network, pass -UseHttp2.

.EXAMPLE
  .\scripts\run_cloudflared_tunnel.ps1 -Token "eyJhIjoi..." -UseHttp2

.EXAMPLE
  .\scripts\run_cloudflared_tunnel.ps1 -TunnelName "dingxiaoding-wecom" -UseHttp2 -Port 8000
#>
param(
    [string]$TunnelName = "",
    [string]$Token = "",
    [int]$Port = 8000,
    [switch]$UseHttp2
)

$cf = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Links\cloudflared.exe"
if (-not (Test-Path $cf)) {
    $cf = "cloudflared"
}

if ($Token) {
    $argList = @("tunnel")
    if ($UseHttp2) {
        $argList += "--protocol", "http2"
    }
    $argList += "run", "--token", $Token
    Write-Host "Running: $cf $($argList -join ' ')" -ForegroundColor Cyan
    & $cf @argList
    exit $LASTEXITCODE
}

if (-not $TunnelName) {
    $TunnelName = "dingxiaoding-wecom"
    Write-Host "No -TunnelName specified; using default: $TunnelName" -ForegroundColor Yellow
}

$argList = @("tunnel")
if ($UseHttp2) {
    $argList += "--protocol", "http2"
}
$argList += "--url", "http://127.0.0.1:$Port", "run", $TunnelName
Write-Host "Running: $cf $($argList -join ' ')" -ForegroundColor Cyan
& $cf @argList
exit $LASTEXITCODE
