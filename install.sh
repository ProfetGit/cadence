#!/bin/sh
# User-local install: launcher, desktop entry, icon. No root needed. Undo with ./install.sh --uninstall
set -e
here="$(cd "$(dirname "$0")" && pwd)"
bin="$HOME/.local/bin"
apps="$HOME/.local/share/applications"
icons="$HOME/.local/share/icons/hicolor/scalable/apps"
plasmoid="$HOME/.local/share/plasma/plasmoids/org.cadence.nowplaying"

if [ "$1" = "--uninstall" ]; then
  rm -f "$bin/cadence" "$bin/cadence-music" "$apps/cadence.desktop" "$icons/cadence.svg" "$HOME/.config/autostart/cadence.desktop"
  rm -rf "$plasmoid"
  update-desktop-database "$apps" 2>/dev/null || true
  gtk-update-icon-cache -q "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
  echo "removed (settings in ~/.config/cadence and cache kept)"
  exit 0
fi

mkdir -p "$bin" "$apps" "$icons"
cat > "$bin/cadence" <<LAUNCH
#!/bin/sh
exec env PYTHONPATH="$here\${PYTHONPATH:+:\$PYTHONPATH}" python3 -m cadence "\$@"
LAUNCH
chmod +x "$bin/cadence"
cp "$bin/cadence" "$bin/cadence-music"
cp "$here/data/cadence.desktop" "$apps/cadence.desktop"
cp "$here/data/cadence.svg" "$icons/cadence.svg"
rm -rf "$plasmoid"
mkdir -p "$(dirname "$plasmoid")"
cp -r "$here/plasmoid/org.cadence.nowplaying" "$plasmoid"
update-desktop-database "$apps" 2>/dev/null || true
gtk-update-icon-cache -q "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
echo "installed: cadence (launcher), desktop entry, icon, Plasma widget 'Cadence Now Playing'"
