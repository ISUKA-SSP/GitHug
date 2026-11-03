param([Parameter(Mandatory=$true)][string]$Target,[Parameter(Mandatory=$true)][string]$Report)
$ErrorActionPreference = 'Stop'
$reportPath = [IO.Path]::GetFullPath($Report)
New-Item -ItemType Directory -Force (Split-Path $reportPath) | Out-Null
$result = [ordered]@{ target=$Target; startedUtc=[DateTime]::UtcNow.ToString('o'); status='error'; scans=@(); files=@() }
try {
    $resolved = (Resolve-Path -LiteralPath $Target).Path
    $commands = @(Get-ChildItem "$env:ProgramData\Microsoft\Windows Defender\Platform\*\MpCmdRun.exe" -ErrorAction SilentlyContinue | Sort-Object FullName -Descending)
    $command = if ($commands.Count) {$commands[0].FullName} else {"$env:ProgramFiles\Windows Defender\MpCmdRun.exe"}
    Update-MpSignature -ErrorAction Stop
    $status = Get-MpComputerStatus
    if (-not $status.AMServiceEnabled -or -not $status.AntivirusEnabled) {throw 'Defender antivirus is unavailable.'}
    $result.engine = $status.AMEngineVersion
    $result.signature = $status.AntivirusSignatureVersion
    $result.signatureUpdated = $status.AntivirusSignatureLastUpdated.ToUniversalTime().ToString('o')
    $paths = @(Get-ChildItem -LiteralPath $resolved -File -Recurse)
    if (Test-Path -LiteralPath $resolved -PathType Leaf) {$paths = @(Get-Item -LiteralPath $resolved)}
    if (-not $paths.Count) {throw 'No files to scan.'}
    $before = @{}
    foreach ($file in $paths) {$before[$file.FullName] = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash}
    $log = & $command -Scan -ScanType 3 -File $resolved -DisableRemediation 2>&1
    $code = $LASTEXITCODE
    $log | Out-File -LiteralPath ($reportPath+'.log') -Encoding utf8
    $result.scans = @(@{exitCode=$code; log=$reportPath+'.log'})
    $detections = @(Get-MpThreatDetection -ErrorAction Stop | Where-Object {$_.InitialDetectionTime.ToUniversalTime() -ge [DateTime]::Parse($result.startedUtc).ToUniversalTime()})
    $result.detections = @($detections | Select-Object ThreatID,Resources,ActionSuccess)
    foreach ($file in $paths) {
        if (-not (Test-Path -LiteralPath $file.FullName)) {throw "File removed during scan: $($file.Name)"}
        $hash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash
        if ($hash -ne $before[$file.FullName]) {throw "File changed during scan: $($file.Name)"}
        $result.files += @{path=$file.FullName; sha256=$hash}
    }
    if ($code -ne 0 -or $detections.Count) {throw 'Scan failed or threats were detected. See logs.'}
    $result.status = 'no_detection'
} catch {
    $result.error = $_.Exception.Message
} finally {
    $result.finishedUtc = [DateTime]::UtcNow.ToString('o')
    $result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $reportPath -Encoding utf8
}
if ($result.status -ne 'no_detection') {throw $result.error}
