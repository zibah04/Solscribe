param([Parameter(Mandatory=$true)][string]$Path)
$ErrorActionPreference = 'Stop'
$thumbprint = $env:SOLSCRIBE_SIGNING_THUMBPRINT
if (-not $thumbprint) {
    Write-Output "UNSIGNED: no signing certificate configured for $Path"
    exit 0
}
if ($thumbprint -notmatch '^[A-Fa-f0-9]{40}$') { throw 'Invalid certificate thumbprint format' }
# A legitimate certificate and its protected private key must already exist in
# the runner certificate store. This script never exports or imports private keys.
$certificate = Get-Item "Cert:\CurrentUser\My\$thumbprint"
if (-not $certificate.HasPrivateKey -or $certificate.NotAfter -lt (Get-Date)) {
    throw 'Signing certificate is expired or has no private key'
}
$signTool = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin\*\x64\signtool.exe" | Sort-Object FullName -Descending | Select-Object -First 1
if (-not $signTool) { throw 'Windows SDK signtool is required for configured signing' }
& $signTool.FullName sign /sha1 $thumbprint /fd SHA256 /tr https://timestamp.digicert.com /td SHA256 $Path
if ($LASTEXITCODE -ne 0) { throw 'Authenticode signing failed' }
& $signTool.FullName verify /pa /all $Path
if ($LASTEXITCODE -ne 0) { throw 'Authenticode verification failed' }
