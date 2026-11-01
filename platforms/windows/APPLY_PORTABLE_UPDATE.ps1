param([Parameter(Mandatory=$true)][string]$PlanPath)
$env:PSModulePath = Join-Path $PSHOME 'Modules'
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
# This helper is launched only after explicit confirmation. It never installs,
# changes the registry, removes directories, or touches the book catalog.
function Absolute([string]$Value) { [IO.Path]::GetFullPath($Value).TrimEnd('\') }
function Save-Plan {
    $temporary = $script:resolvedPlan + '.writing'
    [IO.File]::WriteAllText($temporary, ($script:plan | ConvertTo-Json -Depth 12), [Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $temporary -Destination $script:resolvedPlan -Force
}
function Check-Protected([string]$Target) {
    $absoluteTarget = Absolute $Target
    if ($absoluteTarget -eq [IO.Path]::GetPathRoot($absoluteTarget).TrimEnd('\')) { throw 'Unsafe drive root' }
    foreach ($protected in $script:plan.protectedPaths) {
        $safe = Absolute $protected
        if ($safe -eq $absoluteTarget -or $safe.StartsWith($absoluteTarget+'\',[StringComparison]::OrdinalIgnoreCase) -or $absoluteTarget.StartsWith($safe+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Application overlaps protected library/profile' }
    }
}
function Check-Files([string]$Root) {
    if (((Get-Item -LiteralPath $Root -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'Reparse root not accepted' }
    $allItems = @(Get-ChildItem -LiteralPath $Root -Recurse -Force)
    if (@($allItems | Where-Object { ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 }).Count) { throw 'Reparse files/directories not accepted' }
    $items = @($allItems | Where-Object { -not $_.PSIsContainer })
    $expected = @($script:plan.stagedFiles.PSObject.Properties)
    if ($items.Count -ne $expected.Count) { throw 'Prepared file inventory changed' }
    foreach ($item in $items) {
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'Reparse points not accepted on Windows' }
        $relative = $item.FullName.Substring((Absolute $Root).Length+1).Replace('\','/')
        $entry = $expected | Where-Object Name -CEQ $relative | Select-Object -First 1
        if (-not $entry -or $entry.Value.size -ne $item.Length -or (Get-FileHash -LiteralPath $item.FullName -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.Value.sha256) { throw 'Prepared package changed' }
    }
}
$script:resolvedPlan = Absolute $PlanPath
$privateRoot = Absolute (Join-Path $env:APPDATA 'ManageYourLibrary\updates')
if (-not $resolvedPlan.StartsWith($privateRoot+'\',[StringComparison]::OrdinalIgnoreCase) -or [IO.Path]::GetFileName($resolvedPlan) -ne 'plan.json') { throw 'Plan outside private update state' }
$script:plan = Get-Content -LiteralPath $resolvedPlan -Raw -Encoding UTF8 | ConvertFrom-Json
if ($plan.schema -ne 1 -or $plan.product -ne 'ManageYourLibrary' -or $plan.appId -ne '{A4A5DE08-8644-4D67-B03E-271515180F7D}' -or $plan.target -ne 'windows-portable-x64' -or $plan.state -ne 'handoff_requested') { throw 'Wrong product/platform or missing confirmation' }
$install = Absolute $plan.installRoot
$staged = Absolute $plan.stagedRoot
$rollback = Absolute $plan.rollbackRoot
$session = Split-Path -Parent $resolvedPlan
$expectedStage = Absolute (Join-Path $session 'stage\ManageYourLibrary')
if ($staged -ne $expectedStage -or (Split-Path -Parent $rollback) -ne (Split-Path -Parent $install) -or -not ([IO.Path]::GetFileName($rollback).StartsWith([IO.Path]::GetFileName($install)+'.before-')) -or (Test-Path -LiteralPath $rollback)) { throw 'Unexpected deployment paths' }
Check-Protected $install
Check-Protected $rollback
if (([version]$plan.offer.version) -le ([version]$plan.currentVersion)) { throw 'Downgrade/equal version refused' }
$deadline = [DateTime]::UtcNow.AddSeconds(120)
$plan.state = 'waiting_parent'; Save-Plan
while (Get-Process -Id $plan.ownerPid -ErrorAction SilentlyContinue) {
    if ([DateTime]::UtcNow -gt $deadline) { $plan.state='waiting_parent_timeout'; Save-Plan; throw 'Application still running; no forced termination' }
    Start-Sleep -Milliseconds 200
}
try {
    if ((Get-Content -LiteralPath (Join-Path $install '_internal\VERSION') -Raw).Trim() -ne $plan.currentVersion) { throw 'Installed version changed' }
    $package = Absolute $plan.package
    if ((Split-Path -Parent $package) -ne $session -or (Get-Item -LiteralPath $package).Length -ne $plan.offer.size -or (Get-FileHash -LiteralPath $package -Algorithm SHA256).Hash.ToLowerInvariant() -ne $plan.offer.sha256) { throw 'Downloaded package changed' }
    Check-Files $staged
    $identity = Get-Content -LiteralPath (Join-Path $staged '_internal\update-identity.json') -Raw | ConvertFrom-Json
    if ($identity.product -ne $plan.product -or $identity.version -ne $plan.offer.version -or $identity.platform -ne $plan.target -or $identity.appId -ne $plan.appId) { throw 'Internal update identity mismatch' }
    $newExecutable = Join-Path $staged 'ManageYourLibrary.exe'
    $versionInfo = [Diagnostics.FileVersionInfo]::GetVersionInfo($newExecutable)
    if ($versionInfo.ProductName -ne 'Manage Your Library' -or ([version]$versionInfo.ProductVersion) -ne ([version]$plan.offer.version)) { throw 'Executable identity mismatch' }
    $incoming = Get-AuthenticodeSignature -LiteralPath $newExecutable
    $installed = Get-AuthenticodeSignature -LiteralPath (Join-Path $install 'ManageYourLibrary.exe')
    if ([string]$incoming.Status -notin @('Valid','NotSigned') -or [string]$installed.Status -notin @('Valid','NotSigned')) { throw 'Invalid/untrusted Authenticode signature' }
    if ([string]$installed.Status -eq 'Valid' -and ([string]$incoming.Status -ne 'Valid' -or $incoming.SignerCertificate.Thumbprint -ne $installed.SignerCertificate.Thumbprint)) { throw 'Publisher identity changed' }
    $prepared = $install + '.prepared-' + ([IO.Path]::GetFileName($session).Substring(0,8))
    Check-Protected $prepared
    $plan | Add-Member NoteProperty preparedRoot $prepared -Force
    Save-Plan
    if (-not (Test-Path -LiteralPath $prepared)) { Copy-Item -LiteralPath $staged -Destination $prepared -Recurse }
    Check-Files $prepared
    $plan.state = 'applying'; Save-Plan
    Move-Item -LiteralPath $install -Destination $rollback
    try {
        Move-Item -LiteralPath $prepared -Destination $install
        Start-Process -FilePath (Join-Path $install 'ManageYourLibrary.exe') -WorkingDirectory $install -WindowStyle Hidden
        $plan.state = 'completed'; Save-Plan
    } catch {
        if ((Test-Path -LiteralPath $install) -and -not (Test-Path -LiteralPath $prepared)) { Move-Item -LiteralPath $install -Destination $prepared }
        if (-not (Test-Path -LiteralPath $install)) { Move-Item -LiteralPath $rollback -Destination $install }
        $plan.state = 'rolled_back'; Save-Plan
        throw
    }
} catch {
    $plan | Add-Member NoteProperty error $_.Exception.Message -Force
    if ($plan.state -ne 'rolled_back') { $plan.state = 'needs_recovery' }
    Save-Plan
    throw
}
