param(
    [switch]$ForTesting,
    [string]$SdkRoot = $env:ANDROID_HOME,
    [string]$JavaHome = $env:JAVA_HOME,
    [string]$TestCertificate = '',
    [string]$QaSigningDirectory = '',
    [string]$VersionOverride = '',
    [string]$QaFixturesDirectory = ''
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$version = [IO.File]::ReadAllText((Join-Path $projectRoot 'VERSION')).Trim()
if ($VersionOverride) { if (-not $ForTesting) { throw 'VersionOverride is restricted to QA' }; $version = $VersionOverride }
if ($QaSigningDirectory -and -not $ForTesting) { throw 'QA signing reuse is restricted to QA builds' }
if ($QaFixturesDirectory -and -not $ForTesting) { throw 'QA fixture assets are restricted to QA builds' }
if ($version -notmatch '^\d+\.\d+\.\d+$') { throw 'VERSION must be major.minor.patch' }
if (-not $SdkRoot -or -not (Test-Path -LiteralPath $SdkRoot)) { throw 'Set ANDROID_HOME to the Android SDK directory.' }
if (-not $JavaHome -or -not (Test-Path -LiteralPath (Join-Path $JavaHome 'bin\javac.exe'))) { throw 'Set JAVA_HOME to a JDK (21 or newer).' }
$platform = Join-Path $SdkRoot 'platforms\android-37.0'
if (-not (Test-Path -LiteralPath $platform)) { $platform = Join-Path $SdkRoot 'platforms\android-37' }
$androidJar = Join-Path $platform 'android.jar'
if (-not (Test-Path -LiteralPath $androidJar)) { throw 'Install Android SDK Platform 37 before building.' }
$tools = Join-Path $SdkRoot 'build-tools\36.0.0'
foreach ($tool in @('aapt2.exe', 'aapt.exe', 'zipalign.exe', 'lib\d8.jar', 'lib\apksigner.jar')) {
    if (-not (Test-Path -LiteralPath (Join-Path $tools $tool))) { throw "Missing Android build tool: $tool" }
}
$kind = if ($ForTesting) { 'qa' } else { 'release' }
$work = Join-Path $projectRoot ('dist\android-build\' + $kind + '-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $work | Out-Null
foreach ($name in @('classes','generated','dex','res')) { New-Item -ItemType Directory -Path (Join-Path $work $name) | Out-Null }
$licenses = Join-Path $work 'assets\licenses'
New-Item -ItemType Directory -Path $licenses -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $projectRoot 'LICENSE') -Destination (Join-Path $licenses 'PROJECT_LICENSE.txt')
Copy-Item -LiteralPath (Join-Path $projectRoot 'third_party\indra\MODEL_LICENSE.txt') -Destination $licenses
Copy-Item -LiteralPath (Join-Path $projectRoot 'third_party\indra\NOTICE.txt') -Destination $licenses
if ($ForTesting -and $QaFixturesDirectory) {
    $fixtureDestination = Join-Path $work 'assets\qa'
    New-Item -ItemType Directory -Path $fixtureDestination | Out-Null
    foreach ($fixtureName in @('future.apk','future.update.json','wrong-signer.apk','server.p12')) {
        Copy-Item -LiteralPath (Join-Path $QaFixturesDirectory $fixtureName) -Destination $fixtureDestination
    }
}
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'res\values') -Destination (Join-Path $work 'res') -Recurse
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'res\xml') -Destination (Join-Path $work 'res') -Recurse
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'res\drawable') -Destination (Join-Path $work 'res') -Recurse
$package = 'com.erzod31.manageyourlibrary' + $(if ($ForTesting) { '.qa' } else { '' })
$manifest = [IO.File]::ReadAllText((Join-Path $PSScriptRoot 'AndroidManifest.xml'))
$manifest = $manifest.Replace('package="com.erzod31.manageyourlibrary"', ('package="' + $package + '"'))
$manifest = $manifest.Replace('android:authorities="com.erzod31.manageyourlibrary.files"', ('android:authorities="' + $package + '.files"'))
$manifest = $manifest.Replace('android:authorities="com.erzod31.manageyourlibrary.updates"', ('android:authorities="' + $package + '.updates"'))
$manifest = $manifest.Replace('<application ', ('<application android:debuggable="' + $ForTesting.ToString().ToLowerInvariant() + '" '))
if ($ForTesting) { $manifest = $manifest.Replace('android:label="Mi biblioteca"', 'android:label="Mi biblioteca QA"') }
if ($ForTesting) { $manifest = $manifest.Replace('</manifest>', ('<instrumentation android:name="com.erzod31.manageyourlibrary.QaInstrumentation" android:targetPackage="' + $package + '" /></manifest>')) }
[IO.File]::WriteAllText((Join-Path $work 'AndroidManifest.xml'), $manifest)
if ($ForTesting -and $TestCertificate) {
    New-Item -ItemType Directory -Path (Join-Path $work 'res\raw') | Out-Null
    Copy-Item -LiteralPath $TestCertificate -Destination (Join-Path $work 'res\raw\test_ca.pem')
    [IO.File]::WriteAllText((Join-Path $work 'res\xml\network_security_config.xml'), @'
<?xml version="1.0" encoding="utf-8"?>
<network-security-config>
  <base-config cleartextTrafficPermitted="false"><trust-anchors><certificates src="system" /></trust-anchors></base-config>
  <debug-overrides><trust-anchors><certificates src="@raw/test_ca" /></trust-anchors></debug-overrides>
</network-security-config>
'@)
}
function Check-Exit([string]$step) { if ($LASTEXITCODE -ne 0) { throw "$step failed: $LASTEXITCODE" } }
$aapt2 = Join-Path $tools 'aapt2.exe'
& $aapt2 compile --dir (Join-Path $work 'res') -o (Join-Path $work 'resources.zip'); Check-Exit 'Resource compilation'
$numbers = $version.Split('.')
$versionCode = ([int]$numbers[0] * 1000000) + ([int]$numbers[1] * 1000) + [int]$numbers[2]
& $aapt2 link -o (Join-Path $work 'base.apk') -I $androidJar -A (Join-Path $work 'assets') --manifest (Join-Path $work 'AndroidManifest.xml') `
    --java (Join-Path $work 'generated') --custom-package com.erzod31.manageyourlibrary `
    --min-sdk-version 26 --target-sdk-version 37 --version-name $version --version-code $versionCode (Join-Path $work 'resources.zip')
Check-Exit 'Resource linking'
$sources = @([IO.Directory]::GetFiles((Join-Path $PSScriptRoot 'src'), '*.java', [IO.SearchOption]::AllDirectories)) + @([IO.Directory]::GetFiles((Join-Path $work 'generated'), '*.java', [IO.SearchOption]::AllDirectories))
if ($ForTesting) { $sources += @([IO.Directory]::GetFiles((Join-Path $PSScriptRoot 'qa'), '*.java', [IO.SearchOption]::AllDirectories)) }
$sourceList = Join-Path $work 'sources.txt'
[IO.File]::WriteAllLines($sourceList, @($sources | ForEach-Object { '"' + $_.Replace('\','/') + '"' }))
$bootClasspath = (Join-Path $tools 'core-lambda-stubs.jar') + [IO.Path]::PathSeparator + $androidJar
& (Join-Path $JavaHome 'bin\javac.exe') -encoding UTF-8 -source 8 -target 8 -bootclasspath $bootClasspath -d (Join-Path $work 'classes') "@$sourceList"
Check-Exit 'Java compilation'
$classList = Join-Path $work 'classes.txt'
[IO.File]::WriteAllLines($classList, @([IO.Directory]::GetFiles((Join-Path $work 'classes'), '*.class', [IO.SearchOption]::AllDirectories) | ForEach-Object { $_.Replace('\','/') }))
& (Join-Path $JavaHome 'bin\java.exe') -cp (Join-Path $tools 'lib\d8.jar') com.android.tools.r8.D8 --min-api 26 --lib $androidJar --output (Join-Path $work 'dex') "@$classList"
Check-Exit 'DEX compilation'
$combined = Join-Path $work 'combined.apk'
Copy-Item -LiteralPath (Join-Path $work 'base.apk') -Destination $combined
Push-Location (Join-Path $work 'dex')
try {
    $dexNames = @([IO.Directory]::GetFiles((Join-Path $work 'dex'), '*.dex') | ForEach-Object { [IO.Path]::GetFileName($_) })
    & (Join-Path $tools 'aapt.exe') add $combined @dexNames
    Check-Exit 'Adding DEX with the Android ZIP packager'
} finally { Pop-Location }
# Some Windows SDK ZIP entries retain backslashes. Android treats those as
# filename characters; normalize raw names before alignment and signing.
Add-Type -AssemblyName System.IO.Compression.FileSystem
$normalized = Join-Path $work 'canonical.apk'
$inputArchive = [IO.Compression.ZipFile]::OpenRead($combined)
$outputArchive = [IO.Compression.ZipFile]::Open($normalized, [IO.Compression.ZipArchiveMode]::Create)
try {
    foreach ($entry in $inputArchive.Entries) {
        $entryName = $entry.FullName.Replace([char]0x5c,[char]0x2f)
        $compression = if ($entryName -eq 'resources.arsc') { [IO.Compression.CompressionLevel]::NoCompression } else { [IO.Compression.CompressionLevel]::Optimal }
        $newEntry = $outputArchive.CreateEntry($entryName,$compression)
        $inputStream = $entry.Open(); $outputStream = $newEntry.Open()
        try { $inputStream.CopyTo($outputStream) } finally { $inputStream.Dispose(); $outputStream.Dispose() }
    }
} finally { $inputArchive.Dispose(); $outputArchive.Dispose() }
& (Join-Path $tools 'zipalign.exe') -f 4 $normalized (Join-Path $work 'aligned.apk'); Check-Exit 'APK alignment'
$output = Join-Path $projectRoot $(if ($ForTesting) { 'dist\android-qa\apk' } else { 'dist\android' })
New-Item -ItemType Directory -Path $output -Force | Out-Null
$apk = Join-Path $output ("ManageYourLibrary-$version" + $(if ($ForTesting) { '-qa' } else { '' }) + '.apk')
if (Test-Path -LiteralPath $apk) {
    $archive = Join-Path $output ('archive\' + (Get-FileHash -LiteralPath $apk -Algorithm SHA256).Hash.Substring(0,16))
    New-Item -ItemType Directory -Path $archive -Force | Out-Null
    Copy-Item -LiteralPath $apk -Destination $archive -Force
}
$oldPass = [Environment]::GetEnvironmentVariable('MYL_ANDROID_SIGNING_PASSWORD', 'Process')
try {
    if ($ForTesting) {
        $signDirectory = if ($QaSigningDirectory) { [IO.Path]::GetFullPath($QaSigningDirectory) } else { Join-Path $work 'signing' }
        New-Item -ItemType Directory -Path $signDirectory -Force | Out-Null
        $keyPath = Join-Path $signDirectory 'qa.p12'
        $qaSecret = Join-Path $signDirectory 'password.dpapi'
        if ((Test-Path -LiteralPath $keyPath) -ne (Test-Path -LiteralPath $qaSecret)) { throw 'Incomplete QA signing pair' }
        if (Test-Path -LiteralPath $qaSecret) {
            $secure = Get-Content -LiteralPath $qaSecret -Raw | ConvertTo-SecureString
            $password = [Net.NetworkCredential]::new('', $secure).Password
        } else {
            $password = [Guid]::NewGuid().ToString('N') + [Guid]::NewGuid().ToString('N')
            [IO.File]::WriteAllText($qaSecret, ((ConvertTo-SecureString -String $password -AsPlainText -Force) | ConvertFrom-SecureString))
        }
    } else {
        $signDirectory = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'ManageYourLibraryBuild\signing\android'
        New-Item -ItemType Directory -Path $signDirectory -Force | Out-Null
        $keyPath = Join-Path $signDirectory 'release.p12'; $secretPath = Join-Path $signDirectory 'password.dpapi'
        if ((Test-Path -LiteralPath $keyPath) -ne (Test-Path -LiteralPath $secretPath)) { throw 'Signing key/password pair is incomplete. Restore the signing backup; do not replace the update identity.' }
        if (Test-Path -LiteralPath $secretPath) {
            $secure = Get-Content -LiteralPath $secretPath -Raw | ConvertTo-SecureString
            $password = [Net.NetworkCredential]::new('', $secure).Password
        } else {
            $random = [byte[]]::new(32); $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
            try { $generator.GetBytes($random) } finally { $generator.Dispose() }
            $password = [Convert]::ToBase64String($random)
            $secure = ConvertTo-SecureString -String $password -AsPlainText -Force
            [IO.File]::WriteAllText($secretPath, ($secure | ConvertFrom-SecureString))
        }
    }
    [Environment]::SetEnvironmentVariable('MYL_ANDROID_SIGNING_PASSWORD', $password, 'Process')
    if (-not (Test-Path -LiteralPath $keyPath)) {
        & (Join-Path $JavaHome 'bin\keytool.exe') -genkeypair -noprompt -keystore $keyPath -storetype PKCS12 -alias manageyourlibrary `
            -storepass:env MYL_ANDROID_SIGNING_PASSWORD -keypass:env MYL_ANDROID_SIGNING_PASSWORD -keyalg RSA -keysize 3072 -validity 10000 -dname 'CN=Manage Your Library Android'
        Check-Exit 'Signing key creation'
    }
    & (Join-Path $JavaHome 'bin\java.exe') -jar (Join-Path $tools 'lib\apksigner.jar') sign --ks $keyPath --ks-key-alias manageyourlibrary `
        --ks-pass env:MYL_ANDROID_SIGNING_PASSWORD --key-pass env:MYL_ANDROID_SIGNING_PASSWORD --v1-signing-enabled false --v2-signing-enabled true --v3-signing-enabled true --v4-signing-enabled false --out $apk (Join-Path $work 'aligned.apk')
    Check-Exit 'APK signing'
    $verifiedCertificate = & (Join-Path $JavaHome 'bin\java.exe') -jar (Join-Path $tools 'lib\apksigner.jar') verify --verbose --print-certs --min-sdk-version 26 $apk
    Check-Exit 'APK signature verification'
    $verifiedCertificate | ForEach-Object { Write-Host $_ }
    $certificateMatch = [regex]::Match(($verifiedCertificate -join "`n"), 'Signer #1 certificate SHA-256 digest: ([0-9a-fA-F]{64})')
    if (-not $certificateMatch.Success) { throw 'Missing verified signing certificate digest' }
    $certificateSha = $certificateMatch.Groups[1].Value.ToLowerInvariant()
} finally {
    [Environment]::SetEnvironmentVariable('MYL_ANDROID_SIGNING_PASSWORD', $oldPass, 'Process')
    $password = $null
}
& (Join-Path $tools 'zipalign.exe') -c 4 $apk; Check-Exit 'APK alignment verification'
$fingerprint = (Get-FileHash -LiteralPath $apk -Algorithm SHA256).Hash
$result = [ordered]@{version=$version;versionCode=$versionCode;package=$package;minSdk=26;targetSdk=37;nativeLibraries=0;architecture='universal (platform Java APIs)';sha256=$fingerprint;bytes=(Get-Item -LiteralPath $apk).Length;signingKind=$(if($ForTesting){'qa'}else{'local_private_update_key'});apkPath=$apk;buildDirectory=$work;installationTested=$false}
$inputFiles = @([IO.Directory]::GetFiles($PSScriptRoot, '*', [IO.SearchOption]::AllDirectories) | Where-Object { $ForTesting -or -not $_.StartsWith((Join-Path $PSScriptRoot 'qa') + [IO.Path]::DirectorySeparatorChar) })
$inputFiles += @((Join-Path $projectRoot 'VERSION'),(Join-Path $projectRoot 'LICENSE'),(Join-Path $projectRoot 'third_party\indra\MODEL_LICENSE.txt'),(Join-Path $projectRoot 'third_party\indra\NOTICE.txt'))
$result.sourceInputs = @($inputFiles | Sort-Object -Unique | ForEach-Object { [ordered]@{path=$_.Substring($projectRoot.Length+1).Replace([char]0x5c,[char]0x2f);sha256=(Get-FileHash -LiteralPath $_ -Algorithm SHA256).Hash.ToLowerInvariant()} })
$result.certificateSha256 = $certificateSha
$result.builtAtUtc = [DateTime]::UtcNow.ToString('o')
$result | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $output 'build-manifest.json') -Encoding utf8
[IO.File]::WriteAllText(($apk + '.sha256'), ($fingerprint + '  ' + [IO.Path]::GetFileName($apk) + "`n"))
$update = [ordered]@{schema=1;product='ManageYourLibrary';platform='android-universal';version=$version;versionCode=$versionCode;packageName=$package;name=[IO.Path]::GetFileName($apk);bytes=(Get-Item -LiteralPath $apk).Length;sha256=$fingerprint.ToLowerInvariant();certificateSha256=$certificateSha;minSdk=26;source='desktop_bundle'}
[IO.File]::WriteAllText(([IO.Path]::ChangeExtension($apk, '.update.json')), ($update | ConvertTo-Json -Depth 5), [Text.UTF8Encoding]::new($false))
Write-Host "Android APK ready: $apk"
