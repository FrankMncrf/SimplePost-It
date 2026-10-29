#!/bin/sh
# Instala SimplePost-It para tu usuario en ~/.local (sin gestor de paquetes).
#   ./install.sh               instala o actualiza
#   ./install.sh --uninstall   desinstala (tus notas siguen en Simplenote)
#   ./install.sh --no-deps     instala sin instalar dependencias
# Requisito: la app de escritorio de Simplenote, instalada y con la sesión iniciada.
set -e
cd "$(dirname "$0")"
PREFIX="$HOME/.local"
stop() {  # cerrar la instancia en marcha, si hay
    [ -x "$PREFIX/bin/simplepostit" ] && "$PREFIX/bin/simplepostit" --quit 2>/dev/null || true
    sleep 1
}
if [ "$1" = "--uninstall" ]; then
    stop
    make uninstall PREFIX="$PREFIX"
    rm -f ~/.config/autostart/simplepostit.desktop
    echo "SimplePost-It desinstalado. Tus ajustes siguen en ~/.config/simplepostit y la posición"
    echo "de las notas en ~/.local/state/simplepostit (bórralos si ya no los quieres)."
    exit 0
fi
if [ "$1" != "--no-deps" ] && ! python3 -c 'import PyQt6.QtWidgets' 2>/dev/null; then
    if command -v pacman >/dev/null; then
        sudo pacman -S --needed --noconfirm python python-pyqt6
    elif command -v apt-get >/dev/null; then
        sudo apt-get update && sudo apt-get install -y python3 python3-pyqt6
    elif command -v dnf >/dev/null; then
        sudo dnf install -y python3 python3-pyqt6
    elif command -v zypper >/dev/null; then
        sudo zypper install -y python3 python3-PyQt6
    else
        echo "Instala tú Python 3 y PyQt6 (ver README → Requisitos)." >&2
        exit 1
    fi
fi
if ! command -v simplenote >/dev/null && [ ! -d ~/.config/Simplenote ] && \
        [ ! -d ~/.var/app/com.simplenote.Simplenote ] && [ ! -d ~/snap/simplenote ]; then
    echo "Aviso: no encuentro Simplenote. SimplePost-It es una capa sobre la app de escritorio de" >&2
    echo "Simplenote: instálala (https://simplenote.com) e inicia sesión." >&2
fi
stop
make install PREFIX="$PREFIX" >/dev/null
command -v update-desktop-database >/dev/null && update-desktop-database ~/.local/share/applications 2>/dev/null || true
case ":$PATH:" in *":$PREFIX/bin:"*) ;; *) echo "Aviso: agrega $PREFIX/bin a tu PATH." >&2 ;; esac
if [ -z "$SIMPLEPOSTIT_NO_OPEN" ]; then
    (cd ~ && setsid "$PREFIX/bin/simplepostit" >/dev/null 2>&1 </dev/null &)
    echo "SimplePost-It instalado e iniciado. Ajustes: clic derecho en su ícono de la bandeja."
else
    echo "SimplePost-It instalado."
fi
