#!/bin/sh
# Builds a plain-Python .deb without dpkg tooling (only ar, tar and xz). Usage: build-deb.sh <outdir>
set -e
here="$(cd "$(dirname "$0")/../.." && pwd)"
out="${1:-$here/dist}"
ver="$(python3 -c "import sys; sys.path.insert(0,'$here'); import cadence; print(cadence.__version__)")"
work="$(mktemp -d)"
root="$work/root"
mkdir -p "$root/usr/lib/python3/dist-packages" "$root/usr/bin" "$root/usr/share/applications" \
  "$root/usr/share/icons/hicolor/scalable/apps" "$root/usr/share/plasma/plasmoids" \
  "$root/usr/share/doc/cadence-music" "$work/control"
cp -r "$here/cadence" "$root/usr/lib/python3/dist-packages/"
find "$root" -name __pycache__ -type d -prune -exec rm -rf {} +
cat > "$root/usr/bin/cadence-music" <<'LAUNCH'
#!/usr/bin/python3
import sys
from cadence.__main__ import main
sys.exit(main())
LAUNCH
chmod 755 "$root/usr/bin/cadence-music"
sed 's/^Exec=cadence /Exec=cadence-music /' "$here/data/cadence.desktop" > "$root/usr/share/applications/cadence.desktop"
cp "$here/data/cadence.svg" "$root/usr/share/icons/hicolor/scalable/apps/cadence.svg"
cp -r "$here/plasmoid/org.cadence.nowplaying" "$root/usr/share/plasma/plasmoids/"
cp "$here/LICENSE" "$root/usr/share/doc/cadence-music/copyright"
size="$(du -sk "$root" | cut -f1)"
cat > "$work/control/control" <<CTL
Package: cadence-music
Version: $ver-1
Architecture: all
Maintainer: ProfetGit <54155055+ProfetGit@users.noreply.github.com>
Installed-Size: $size
Depends: python3 (>= 3.10), python3-pyqt6, python3-pyqt6.qtwebengine, python3-pyqt6.qtsvg, python3-pyqt6.qtwebchannel, python3-gi, gir1.2-glib-2.0
Recommends: kde-plasma-desktop | plasma-workspace
Section: sound
Priority: optional
Homepage: https://github.com/ProfetGit/cadence
Description: Native-feeling YouTube Music player
 Qt 6 shell around music.youtube.com with a native player bar, MPRIS2,
 tray icon, synced lyrics, a mini player and a Plasma widget.
CTL
( cd "$root" && find . -type f -exec md5sum {} + | sed 's# \./# #' > "$work/control/md5sums" )
( cd "$work/control" && tar --owner=0 --group=0 -cJf "$work/control.tar.xz" . )
( cd "$root" && tar --owner=0 --group=0 -cJf "$work/data.tar.xz" . )
echo "2.0" > "$work/debian-binary"
mkdir -p "$out"
deb="$out/cadence-music_${ver}-1_all.deb"
rm -f "$deb"
( cd "$work" && ar rc "$deb" debian-binary control.tar.xz data.tar.xz )
rm -rf "$work"
echo "$deb"
