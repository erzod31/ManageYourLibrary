param(
    [Parameter(Mandatory = $true)]
    [string]$CertificateThumbprint,
    [string]$TimestampUrl = "http://timestamp.digicert.com"
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$targets = @(
    (Join-Path $root "dist\windows\ManageYourLibrary\ManageYourLibrary.exe")
)
$installer = Get-ChildItem -LiteralPath (Join-Path $root "dist\installer") -Filter "ManageYourLibrary-*-Setup-x64.exe" -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($installer) { $targets += $installer.FullName }

$signtool = (Get-Command signtool.exe -ErrorAction Stop).Source
foreach ($target in $targets) {
    if (-not (Test-Path -LiteralPath $target)) { throw "Missing artifact: $target" }
    & $signtool sign /sha1 $CertificateThumbprint /fd SHA256 /tr $TimestampUrl /td SHA256 $target
    if ($LASTEXITCODE -ne 0) { throw "Signing failed: $target" }
    & $signtool verify /pa /all $target
    if ($LASTEXITCODE -ne 0) { throw "Signature verification failed: $target" }
}
