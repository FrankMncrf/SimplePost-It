#!/bin/bash
# Instala (o actualiza) SimplePost-It en macOS sin pasar por Gatekeeper:
#   curl -fsSL https://raw.githubusercontent.com/FrankMncrf/SimplePost-It/main/packaging/macos/install.sh | bash
# curl no marca lo que descarga como «bajado de internet» (com.apple.quarantine), que es lo
# que hace que macOS rechace una app sin firma de un desarrollador de pago.
set -euo pipefail

REPO="FrankMncrf/SimplePost-It"
case "$(uname -m)" in
    arm64) arch=arm64 ;;
    x86_64) arch=x86_64 ;;
    *) echo "Arquitectura no compatible: $(uname -m)" >&2; exit 1 ;;
esac

echo "Buscando la última versión…"
url=$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" \
      | grep -o "\"browser_download_url\": *\"[^\"]*-macos-$arch\.dmg\"" | head -1 | sed 's/.*"\(https[^"]*\)"/\1/')
[ -n "$url" ] || { echo "No hay un .dmg para $arch en la última versión." >&2; exit 1; }

tmp=$(mktemp -d)
trap 'hdiutil detach -quiet "$tmp/mnt" 2>/dev/null || true; rm -rf "$tmp"' EXIT
echo "Descargando $(basename "$url")…"
curl -fL --progress-bar -o "$tmp/app.dmg" "$url"
hdiutil attach -nobrowse -quiet -mountpoint "$tmp/mnt" "$tmp/app.dmg"

# /Applications si se puede escribir ahí; si no, ~/Applications (sin pedir contraseña)
dest=/Applications
[ -w "$dest" ] || { dest="$HOME/Applications"; mkdir -p "$dest"; }
if [ -d "$dest/SimplePost-It.app" ]; then
    "$dest/SimplePost-It.app/Contents/MacOS/SimplePost-It" --quit 2>/dev/null || true
    rm -rf "$dest/SimplePost-It.app"
fi
ditto "$tmp/mnt/SimplePost-It.app" "$dest/SimplePost-It.app"
xattr -dr com.apple.quarantine "$dest/SimplePost-It.app" 2>/dev/null || true

echo "Instalado en $dest/SimplePost-It.app"
[ "${SIMPLEPOSTIT_NO_OPEN:-}" ] || open "$dest/SimplePost-It.app"
