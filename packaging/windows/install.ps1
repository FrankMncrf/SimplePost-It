# Instala (o actualiza) SimplePost-It en Windows desde PowerShell:
#   irm https://raw.githubusercontent.com/FrankMncrf/SimplePost-It/main/packaging/windows/install.ps1 | iex
# Lo descargado asi no lleva la marca "bajado de internet" (Mark of the Web), que es lo que
# hace que SmartScreen frene un instalador sin firma. Se instala solo para el usuario,
# sin permisos de administrador.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'   # Invoke-WebRequest es mucho mas rapido sin barra
$repo = 'FrankMncrf/SimplePost-It'

Write-Host 'Buscando la ultima version...'
$release = Invoke-RestMethod "https://api.github.com/repos/$repo/releases/latest"
$asset = $release.assets | Where-Object { $_.name -like '*-windows-setup.exe' } | Select-Object -First 1
if (-not $asset) { throw 'No hay instalador de Windows en la ultima version.' }

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
