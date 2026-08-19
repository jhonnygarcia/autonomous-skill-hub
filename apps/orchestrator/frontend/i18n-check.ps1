# Cuenta lineas con texto espanol visible fuera de comentarios. ASCII-only:
# Windows PowerShell 5.1 lee los .ps1 como ANSI y mastica los acentos del fuente.
param([string]$Root = "$PSScriptRoot\src", [string[]]$Only = @())
# `-File script.ps1 -Only a,b` hands PowerShell a SINGLE string "a,b", not two
# elements -- split any element that contains a comma so both invocation forms
# (direct array call and `-File ... -Only a,b`) land on the same list.
$Only = @($Only | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim() } | Where-Object { $_ })
$L = 'a-zA-Z\u00e1\u00e9\u00ed\u00f3\u00fa\u00f1\u00c1\u00c9\u00cd\u00d3\u00da\u00d1'
$words = @('el','la','los','las','un','una','de','del','que','para','con','sin','por',
           'no','se','es','son','hay','cada','todo','todos','esta','este','su','sus',
           'al','lo','pero','como','cuando','donde','desde','hasta','entre','sobre',
           'corrida','corridas','fase','fases','proyecto','ticket','tickets','rama',
           'repo','repos','nada','guardar','cancelar','borrar','ejecutar','continuar',
           'responder','aceptar','abrir','nuevo','nueva','editar','volver','idioma',
           'entregable','decisiones','archivo','ajustes','modelo','motor','esfuerzo')
$re = '(?i)(^|[^' + $L + '])(' + ($words -join '|') + ')($|[^' + $L + '])'
$accent = '[\u00e1\u00e9\u00ed\u00f3\u00fa\u00f1\u00c1\u00c9\u00cd\u00d3\u00da\u00d1\u00bf\u00a1]'
$total = 0
$scanned = 0
$allFiles = Get-ChildItem $Root -Recurse -Include *.tsx, *.ts
$targets = $allFiles
if ($Only.Count) {
    $targets = $allFiles | Where-Object { $Only -contains $_.Name }
    if (-not $targets) {
        [Console]::Error.WriteLine("i18n-check.ps1: -Only asked for [$($Only -join ', ')] but $Root has no matching file. Files present: [$(($allFiles | ForEach-Object { $_.Name }) -join ', ')]")
        exit 1
    }
}
foreach ($f in $targets) {
    if ($f.Name -eq 'strings.ts') { continue }   # el diccionario ES vive ahi a proposito
    $scanned++
    $inBlock = $false; $n = 0
    foreach ($ln in (Get-Content $f.FullName -Encoding UTF8)) {
        if ($inBlock) { if ($ln -match '\*/') { $inBlock = $false }; continue }
        # `{/* ... */}` is a JSX comment -- same treatment as a plain `/* ... */`
        # block, just with an optional leading `{`. A line that opens AND closes
        # the comment (the common single-line JSX case) is skipped outright below
        # without ever setting $inBlock.
        if ($ln -match '^\s*\{?/\*') { if ($ln -notmatch '\*/') { $inBlock = $true }; continue }
        if ($ln -match '^\s*(//|\*)') { continue }
        if ($ln -notmatch '["''`>]') { continue }
        $s = [regex]::Replace($ln, 'className=(\{?"[^"]*"\}?|\{`[^`]*`\})', '')
        $s = [regex]::Replace($s, '(from|import)\s+["''][^"'']+["'']', '')
        if ($s -match $re -or $s -match $accent) { $n++ }
    }
    if ($n) { "{0,-20} {1,3}" -f $f.Name, $n; $total += $n }
}
"SCANNED: $scanned files"
"TOTAL: $total"
