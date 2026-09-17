[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName System.Security -ErrorAction Stop
Import-Module (Join-Path $PSHOME 'Modules\Microsoft.PowerShell.Security\Microsoft.PowerShell.Security.psd1') -Force -ErrorAction Stop

if (-not $env:LOCALAPPDATA) {
    throw 'LOCALAPPDATA is unavailable. This setup is supported on Windows only.'
}

$secureKey = $null
$bstr = [IntPtr]::Zero
$plainBytes = $null
$plainText = $null
$protectedBytes = $null
$failure = $null
$stage = 'prompt'

try {
    $secureKey = Read-Host 'Paste your Gemini API key (input is hidden)' -AsSecureString
    $stage = 'convert'
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
    $plainText = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    if ([string]::IsNullOrWhiteSpace($plainText)) {
        throw 'No key was entered. Nothing was saved.'
    }

    $plainBytes = [Text.Encoding]::UTF8.GetBytes($plainText.Trim())
    $stage = 'protect'
    $protectedBytes = [Security.Cryptography.ProtectedData]::Protect(
        $plainBytes,
        $null,
        [Security.Cryptography.DataProtectionScope]::CurrentUser
    )

    $stage = 'write'
    $targetDirectory = Join-Path $env:LOCALAPPDATA 'Ngeebula'
    $targetPath = Join-Path $targetDirectory 'gemini-key.dpapi'
    [IO.Directory]::CreateDirectory($targetDirectory) | Out-Null
    [IO.File]::WriteAllText(
        $targetPath,
        [Convert]::ToBase64String($protectedBytes),
        [Text.Encoding]::ASCII
    )
}
catch {
    $failure = $_.Exception
}
finally {
    if ($plainBytes) {
        [Array]::Clear($plainBytes, 0, $plainBytes.Length)
    }
    if ($protectedBytes) {
        [Array]::Clear($protectedBytes, 0, $protectedBytes.Length)
    }
    $plainText = $null
    if ($bstr -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
    if ($secureKey) {
        $secureKey.Dispose()
    }
}

if ($failure) {
    $failureType = $failure.GetType().FullName
    $failureCode = ('0x{0:X8}' -f ($failure.HResult -band 0xffffffffL))
    throw "Gemini credential setup failed at $stage ($failureType, $failureCode). No secret was printed."
}

Write-Host 'Gemini credential saved for the current Windows user.'
Write-Host 'The running Ngeebula backend can detect it without a restart.'
