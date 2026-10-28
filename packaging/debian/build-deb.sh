#!/bin/sh
# Build simplepostit_<version>-1_all.deb into ./dist (run from the source tree).
set -eu
VERSION=$(sed -n 's/^VERSION = "\(.*\)"/\1/p' simplepostit.py)
ROOT=$(mktemp -d)
trap 'rm -rf "$ROOT"' EXIT
make install DESTDIR="$ROOT" PREFIX=/usr LICENSEDIR=/usr/share/doc/simplepostit
mv "$ROOT/usr/share/doc/simplepostit/LICENSE" "$ROOT/usr/share/doc/simplepostit/copyright"
gzip -9n -c CHANGELOG.md > "$ROOT/usr/share/doc/simplepostit/changelog.gz"
mkdir -p "$ROOT/DEBIAN"
sed "s/@VERSION@/$VERSION/" packaging/debian/control.in > "$ROOT/DEBIAN/control"
echo "Installed-Size: $(du -sk "$ROOT/usr" | cut -f1)" >> "$ROOT/DEBIAN/control"
mkdir -p dist
dpkg-deb --root-owner-group -Zxz --build "$ROOT" "dist/simplepostit_${VERSION}-1_all.deb"
