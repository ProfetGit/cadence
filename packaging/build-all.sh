#!/bin/sh
# Builds every release artifact into ./dist from the current git HEAD. Needs: git, python-build, makepkg, flatpak-builder.
set -e
here="$(cd "$(dirname "$0")/.." && pwd)"
cd "$here"
ver="$(python3 -c "import sys; sys.path.insert(0,'.'); import cadence; print(cadence.__version__)")"
dist="$here/dist"
rm -rf "$dist" && mkdir -p "$dist"

git archive --format=tar.gz --prefix="cadence-$ver/" -o "$dist/cadence-$ver.tar.gz" HEAD
python3 -m build --no-isolation --outdir "$dist" >/dev/null

work="$(mktemp -d)"
cp packaging/arch/PKGBUILD "$work/"
cp "$dist/cadence-$ver.tar.gz" "$work/cadence-$ver.tar.gz"
sed -i "s#^source=.*#source=(\"cadence-\$pkgver.tar.gz\")#" "$work/PKGBUILD"
( cd "$work" && makepkg -f --nodeps --skipinteg >"$work/makepkg.log" 2>&1 || { cat "$work/makepkg.log"; exit 1; } )
cp "$work"/cadence-music-*.pkg.tar.zst "$dist/"
rm -rf "$work"

packaging/debian/build-deb.sh "$dist" >/dev/null

if command -v flatpak >/dev/null 2>&1 && flatpak info org.flatpak.Builder >/dev/null 2>&1; then
  b="$(mktemp -d)"
  flatpak run org.flatpak.Builder --user --force-clean --disable-rofiles-fuse --repo="$b/repo" "$b/build" \
    packaging/flatpak/io.github.ProfetGit.Cadence.yml
  flatpak build-bundle "$b/repo" "$dist/io.github.ProfetGit.Cadence.flatpak" io.github.ProfetGit.Cadence
  rm -rf "$b"
fi
( cd "$dist" && sha256sum * > SHA256SUMS )
ls -la "$dist"
