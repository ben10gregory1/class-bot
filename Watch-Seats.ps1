<#
  Watch-Seats.ps1 - College of Charleston open-seat watcher
  Polls CofC's PUBLIC Banner "Browse Classes" API and alerts you the
  moment any watched section has an open seat. No login / Duo required.

  Quick start:
    1. Edit the CONFIG block below (at minimum, set $NtfyTopic to your own
       secret-ish name, e.g. "cofc-ben-math104-9x2").
    2. Install the "ntfy" app on your phone (App Store / Play Store), open it,
       and Subscribe to that exact topic name.
    3. Run:  powershell -ExecutionPolicy Bypass -File .\Watch-Seats.ps1
    4. Leave the window open. You'll get a push the instant a seat frees up.
#>

# ============================== CONFIG ==============================
$Term        = "202710"          # 202710 = Fall 2026, 202630 = Summer 2026
$Subject     = "MATH"
$CourseNum   = "104"
$WatchCRNs   = @()               # empty = ALL sections; or e.g. @("10288","12154")
$PollSeconds = 60                # how often to check (don't go below ~30)
$RenotifyEvery = 0               # 0 = alert once per opening; or minutes to re-nag while still open

# --- Notification methods (turn on as many as you like) ---
$UseNtfy    = $true
$NtfyTopic  = "cofc-ben-math104-9x2"   # <-- subscribe to this in the ntfy app

$UseEmail   = $false
$EmailTo    = "ben10gregory1@gmail.com"
$EmailFrom  = "your.gmail@gmail.com"            # a Gmail you control
$EmailAppPw = ""                                # Gmail App Password (not your normal password)

$UseDesktop = $true              # console banner + beep on this PC
# ===================================================================

$Base = "https://ssb.cofc.edu/StudentRegistrationSsb/ssb"
$Jar  = Join-Path $env:TEMP "cofc_seatbot_cookies.txt"
$RegisterLink = "https://ssb.cofc.edu/StudentRegistrationSsb/ssb/term/termSelection?mode=search"

# Log everything (console output + errors) to watch.log next to this script.
# Harmless when run interactively; essential when run as a hidden scheduled task.
$LogFile = Join-Path $PSScriptRoot "watch.log"
try { Start-Transcript -Path $LogFile -Append -ErrorAction SilentlyContinue | Out-Null } catch {}

function Get-Sections {
    # Re-prime a fresh session each poll (cheap + robust against session expiry)
    if (Test-Path $Jar) { Remove-Item $Jar -Force -ErrorAction SilentlyContinue }
    & curl.exe -s -c $Jar -b $Jar -o NUL --max-time 25 "$Base/term/termSelection?mode=search" | Out-Null
    & curl.exe -s -c $Jar -b $Jar -o NUL --max-time 25 -X POST "$Base/term/search?mode=search" `
        --data-urlencode "term=$Term" --data-urlencode "studyPath=" `
        --data-urlencode "startDatepicker=" --data-urlencode "endDatepicker=" | Out-Null

    $url = "$Base/searchResults/searchResults?txt_subject=$Subject&txt_courseNumber=$CourseNum" +
           "&txt_term=$Term&pageOffset=0&pageMaxSize=100&sortColumn=subjectDescription&sortDirection=asc"
    $raw = & curl.exe -s -c $Jar -b $Jar --max-time 25 $url
    if (-not $raw) { throw "empty response from Banner" }
    $parsed = $raw | ConvertFrom-Json
    return $parsed.data
}

function Send-Alert {
    param([string]$Title, [string]$Body)

    if ($UseNtfy) {
        try {
            Invoke-RestMethod -Uri "https://ntfy.sh/$NtfyTopic" -Method Post `
                -Body ([System.Text.Encoding]::UTF8.GetBytes($Body)) `
                -Headers @{ Title = $Title; Priority = "urgent"; Tags = "rotating_light" } | Out-Null
        } catch { Write-Host "  [ntfy failed: $($_.Exception.Message)]" -ForegroundColor DarkYellow }
    }

    if ($UseEmail) {
        try {
            $sec = ConvertTo-SecureString $EmailAppPw -AsPlainText -Force
            $cred = New-Object System.Management.Automation.PSCredential ($EmailFrom, $sec)
            Send-MailMessage -To $EmailTo -From $EmailFrom -Subject $Title -Body $Body `
                -SmtpServer "smtp.gmail.com" -Port 587 -UseSsl -Credential $cred
        } catch { Write-Host "  [email failed: $($_.Exception.Message)]" -ForegroundColor DarkYellow }
    }

    if ($UseDesktop) {
        Write-Host ""
        Write-Host "  ============================================" -ForegroundColor Green
        Write-Host "   $Title" -ForegroundColor Green
        Write-Host "   $Body" -ForegroundColor Green
        Write-Host "  ============================================" -ForegroundColor Green
        Write-Host ""
        for ($i=0; $i -lt 3; $i++) { [console]::Beep(880,250); [console]::Beep(1175,250) }
    }
}

# Tracks CRNs we've already alerted on, plus when, to avoid spamming.
$notified = @{}

Write-Host "CofC seat watcher started." -ForegroundColor Cyan
Write-Host ("Watching {0} {1} ({2}) | sections: {3} | every {4}s" -f `
    $Subject, $CourseNum, $Term, $(if ($WatchCRNs.Count) { $WatchCRNs -join "," } else { "ALL" }), $PollSeconds) -ForegroundColor Cyan
if ($UseNtfy -and $NtfyTopic -eq "CHANGE-ME-to-something-secret") {
    Write-Host "WARNING: You haven't set `$NtfyTopic - ntfy alerts won't reach you until you do." -ForegroundColor Red
}
Write-Host "Press Ctrl+C to stop.`n" -ForegroundColor DarkGray

while ($true) {
    $stamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    try {
        $sections = Get-Sections
        if ($WatchCRNs.Count) {
            $sections = $sections | Where-Object { $WatchCRNs -contains $_.courseReferenceNumber }
        }

        $openNow = $sections | Where-Object { [int]$_.seatsAvailable -gt 0 }
        $openCount = @($openNow).Count
        Write-Host ("[{0}] checked {1} sections - {2} open" -f $stamp, @($sections).Count, $openCount) -ForegroundColor DarkGray

        foreach ($s in $openNow) {
            $crn = $s.courseReferenceNumber
            $key = "$crn"
            $shouldNotify = $false
            if (-not $notified.ContainsKey($key)) {
                $shouldNotify = $true
            } elseif ($RenotifyEvery -gt 0) {
                $mins = ((Get-Date) - $notified[$key]).TotalMinutes
                if ($mins -ge $RenotifyEvery) { $shouldNotify = $true }
            }

            if ($shouldNotify) {
                $sec = "{0} {1}-{2}" -f $s.subject, $s.courseNumber, $s.sequenceNumber
                $title = "SEAT OPEN: $sec"
                $body  = "{0} (CRN {1}) has {2} seat(s) open! Register: {3}" -f `
                         $sec, $crn, $s.seatsAvailable, $RegisterLink
                Send-Alert -Title $title -Body $body
                $notified[$key] = Get-Date
            }
        }

        # Reset any section that has closed again, so a future opening re-alerts.
        $openKeys = @($openNow | ForEach-Object { "$($_.courseReferenceNumber)" })
        foreach ($k in @($notified.Keys)) {
            if ($openKeys -notcontains $k) { $notified.Remove($k) }
        }
    }
    catch {
        Write-Host ("[{0}] check failed: {1} (will retry)" -f $stamp, $_.Exception.Message) -ForegroundColor DarkYellow
    }

    Start-Sleep -Seconds $PollSeconds
}
