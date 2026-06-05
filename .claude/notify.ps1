param(
  [ValidateSet("Stop", "Notification")]
  [string]$Event = "Stop"
)

$ErrorActionPreference = "SilentlyContinue"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogPath = Join-Path $Root "hook-notify.log"

Add-Content -Path $LogPath -Value "$Event fired: $(Get-Date -Format o)"

function Play-CustomWav {
  param([string]$Path)

  if (Test-Path $Path) {
    $player = New-Object System.Media.SoundPlayer $Path
    $player.PlaySync()
    return $true
  }

  return $false
}

function Play-BeepPattern {
  param([string]$Mode)

  if ($Mode -eq "Stop") {
    [Console]::Beep(880, 180)
    Start-Sleep -Milliseconds 120
    [Console]::Beep(1175, 220)
    Start-Sleep -Milliseconds 120
    [Console]::Beep(1568, 260)
  }
  else {
    1..4 | ForEach-Object {
      [Console]::Beep(1200, 180)
      Start-Sleep -Milliseconds 100
      [Console]::Beep(800, 180)
      Start-Sleep -Milliseconds 160
    }
  }
}

if ($Event -eq "Stop") {
  $doneWav = Join-Path $Root "done.wav"

  if (-not (Play-CustomWav $doneWav)) {
    Play-BeepPattern "Stop"
  }
}
else {
  $attentionWav = Join-Path $Root "attention.wav"

  if (-not (Play-CustomWav $attentionWav)) {
    Play-BeepPattern "Notification"
  }
}
