<#
.SYNOPSIS
  Create SSH reverse tunnel from server to local FastAPI.

.DESCRIPTION
  Use when app runs only on your laptop, but public domain/nginx is on server.
  This command exposes local 127.0.0.1:LocalPort as server 127.0.0.1:RemotePort.

.EXAMPLE
  .\scripts\run_reverse_ssh_tunnel.ps1 -SshUser "alice" -SshHost "agent.gilitel.com" -RemotePort 18000 -LocalPort 8000
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$SshUser,
    [Parameter(Mandatory = $true)]
    [string]$SshHost,
    [int]$RemotePort = 18000,
    [int]$LocalPort = 8000
)

$sshCmd = @(
    "-NT",
    "-o", "ServerAliveInterval=30",
    "-o", "ServerAliveCountMax=3",
    "-o", "ExitOnForwardFailure=yes",
    "-R", "127.0.0.1:$RemotePort`:127.0.0.1:$LocalPort",
    "$SshUser@$SshHost"
)

Write-Host "Running reverse tunnel:" -ForegroundColor Cyan
Write-Host ("ssh " + ($sshCmd -join " ")) -ForegroundColor Yellow
Write-Host "Keep this terminal open while testing." -ForegroundColor Cyan

ssh @sshCmd
exit $LASTEXITCODE
