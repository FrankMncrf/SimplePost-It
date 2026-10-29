#!/bin/bash
# Instala (o actualiza) SimplePost-It en Linux con el paquete de tu distribución:
#   curl -fsSL https://raw.githubusercontent.com/FrankMncrf/SimplePost-It/main/packaging/linux/install.sh | bash
# Arch/CachyOS/Manjaro (.pkg.tar.zst), Debian/Ubuntu/Mint (.deb), Fedora/openSUSE (.rpm); en
# otras, o con SIMPLEPOSTIT_USER=1, se instala desde el código solo para tu usuario (~/.local).
set -euo pipefail

REPO="FrankMncrf/SimplePost-It"
SUDO=""
[ "$(id -u)" -eq 0 ] || SUDO="sudo"

if [ -z "${SIMPLEPOSTIT_USER:-}" ]; then
    if command -v pacman >/dev/null; then kind="pkg.tar.zst"
    elif command -v apt-get >/dev/null; then kind="deb"
    elif command -v dnf >/dev/null || command -v zypper >/dev/null; then kind="rpm"
    else kind="source"
    fi
else
    kind="source"
fi

echo "Buscando la última versión…"
# sin la API de GitHub (limita las consultas anónimas): la página de la última versión
tag=$(curl -fsSLo /dev/null -w '%{url_effective}' "https://github.com/$REPO/releases/latest")
tag=${tag##*/}
case "$tag" in v[0-9]*) ;; *) echo "No pude consultar las versiones en GitHub." >&2; exit 1 ;; esac

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

# cerrar la versión en marcha antes de actualizar
command -v simplepostit >/dev/null && simplepostit --quit 2>/dev/null || true

if [ "$kind" = "source" ]; then
    echo "Instalando $tag desde el código, solo para tu usuario…"
    curl -fsSL "https://github.com/$REPO/archive/refs/tags/$tag.tar.gz" | tar -xz -C "$tmp"
    [ "${SIMPLEPOSTIT_NO_OPEN:-}" ] && export SIMPLEPOSTIT_NO_OPEN
    sh "$tmp"/SimplePost-It-*/install.sh
    exit 0
fi

path=$(curl -fsSL "https://github.com/$REPO/releases/expanded_assets/$tag" \
       | grep -o "/$REPO/releases/download/$tag/[^\"]*\.$kind" | head -1)
[ -n "$path" ] || { echo "No hay paquete .$kind en $tag." >&2; exit 1; }
url="https://github.com$path"
file="$tmp/$(basename "$url")"
echo "Descargando $(basename "$url")…"
curl -fL --progress-bar -o "$file" "$url"

echo "Instalando (puede pedir tu contraseña)…"
case "$kind" in
    pkg.tar.zst) $SUDO pacman -U --needed --noconfirm "$file" ;;
    deb) $SUDO apt-get update -qq && $SUDO apt-get install -y "$file" ;;
    rpm) if command -v dnf >/dev/null; then $SUDO dnf install -y "$file"
         else $SUDO zypper --non-interactive install --allow-unsigned-rpm "$file"; fi ;;
esac

# una instalación anterior solo para el usuario taparía a la del paquete (va antes en el PATH)
if [ -e "$HOME/.local/bin/simplepostit" ]; then
    echo "Aviso: también tienes SimplePost-It instalado en ~/.local (desde el código), que se usa" >&2
    echo "en lugar del paquete. Quítalo con:  rm -rf ~/.local/bin/simplepostit ~/.local/lib/simplepostit" >&2
fi
if ! command -v simplenote >/dev/null && [ ! -d "$HOME/.config/Simplenote" ] && \
        [ ! -d "$HOME/.var/app/com.simplenote.Simplenote" ] && [ ! -d "$HOME/snap/simplenote" ]; then
    echo "Aviso: no encuentro Simplenote. SimplePost-It es una capa sobre la app de escritorio de" >&2
    echo "Simplenote: instálala (https://simplenote.com) e inicia sesión." >&2
fi

echo "SimplePost-It $tag instalado."
if [ -z "${SIMPLEPOSTIT_NO_OPEN:-}" ] && [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then
    (cd ~ && setsid simplepostit >/dev/null 2>&1 </dev/null &)
fi
