# Instala (o actualiza) SimplePost-It en Windows desde PowerShell:
#   irm https://raw.githubusercontent.com/FrankMncrf/SimplePost-It/main/packaging/windows/install.ps1 | iex
# Lo descargado asi no lleva la marca "bajado de internet" (Mark of the Web), que es lo que
# hace que SmartScreen frene un instalador sin firma. Se instala solo para el usuario,
# sin permisos de administrador.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'   # Invoke-WebRequest es mucho mas rapido sin barra
$repo = 'FrankMncrf/SimplePost-It'

Write-Host 'Buscando la ultima version...'
# sin la API de GitHub (limita las consultas anonimas): la pagina de la ultima version
$page = Invoke-WebRequest "https://github.com/$repo/releases/latest" -UseBasicParsing
$tag = [regex]::Match($page.Content, "/$repo/releases/tag/(v[0-9][^`"/?#]*)").Groups[1].Value
if (-not $tag) { throw 'No pude consultar las versiones en GitHub.' }
$assets = Invoke-WebRequest "https://github.com/$repo/releases/expanded_assets/$tag" -UseBasicParsing
$path = [regex]::Match($assets.Content, "/$repo/releases/download/$tag/[^`"]*-windows-setup\.exe").Value
if (-not $path) { throw "No hay instalador de Windows en $tag." }
$asset = [pscustomobject]@{ name = $path.Split('/')[-1]; browser_download_url = "https://github.com$path" }
$release = [pscustomobject]@{ tag_name = $tag }

$setup = Join-Path $env:TEMP $asset.name
Write-Host "Descargando $($asset.name)..."
Invoke-WebRequest $asset.browser_download_url -OutFile $setup
Unblock-File $setup   # por si acaso: quita la marca si la hubiera

$exe = Join-Path $env:LOCALAPPDATA 'Programs\SimplePost-It\SimplePost-It.exe'
if (Test-Path $exe) { & $exe --quit; Start-Sleep 2 }   # actualizar: cerrar la version abierta

Write-Host 'Instalando...'
$p = Start-Process $setup -ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART' -Wait -PassThru
Remove-Item $setup -ErrorAction SilentlyContinue
if ($p.ExitCode -ne 0) { throw "El instalador termino con el codigo $($p.ExitCode)." }

Write-Host "SimplePost-It $($release.tag_name) instalado."
if ((Test-Path $exe) -and -not $env:SIMPLEPOSTIT_NO_OPEN) { Start-Process $exe }
