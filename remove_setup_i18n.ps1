$files = @('zh.json','en.json','ja.json','ko.json')
foreach ($f in $files) {
    $path = "mingtang\src\i18n\locales\$f"
    $lines = Get-Content $path -Encoding UTF8
    $newLines = [System.Collections.Generic.List[string]]::new()
    $inSetupPage = $false
    $braceDepth = 0
    foreach ($line in $lines) {
        if ($line -match '"configWizardDesc"|"rerunSetup"|"confirmRerunSetup"|"confirmRerunSetupDesc"') {
            continue
        }
        if ($line -match '^\s*"setupPage"\s*:\s*\{') {
            $inSetupPage = $true
            $braceDepth = 1
            continue
        }
        if ($inSetupPage) {
            $opens = ([regex]::Matches($line, '\{')).Count
            $closes = ([regex]::Matches($line, '\}')).Count
            $braceDepth += $opens - $closes
            if ($braceDepth -le 0) {
                $inSetupPage = $false
                continue
            }
            continue
        }
        $newLines.Add($line)
    }
    $newLines | Set-Content $path -Encoding UTF8
    $removedCount = $lines.Count - $newLines.Count
    Write-Host "$f: 删除 $removedCount 行"
}