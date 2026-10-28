#!/usr/bin/env bash
# Build GitDesk for Linux (x86_64): .deb installer + portable .tar.gz
# Usage (from the project root):  bash packaging/linux/build_linux.sh
set -euo pipefail
cd "$(dirname "$0")/../.."
ROOT=$PWD
VERSION=$(python3 -c "import re;print(re.search(r'__version__ = \"(.+)\"', open('gitdesk/__init__.py').read()).group(1))")
ARCH=$(dpkg --print-architecture 2>/dev/null || echo amd64)

if [ -z "${SKIP_VENV:-}" ]; then
  python3 -m venv .venv-build
  . .venv-build/bin/activate
  pip install --upgrade pip >/dev/null
  pip install -r requirements.txt pyinstaller
fi

python3 packaging/make_icons.py
pyinstaller packaging/gitdesk.spec --noconfirm --distpath dist --workpath build

# ---------- .deb ----------
PKG=build/deb/gitdesk_${VERSION}_${ARCH}
rm -rf "$PKG"
mkdir -p "$PKG/DEBIAN" "$PKG/opt/gitdesk" "$PKG/usr/bin" "$PKG/usr/share/applications" \
         "$PKG/usr/share/icons/hicolor/256x256/apps"
cp -a dist/GitDesk/. "$PKG/opt/gitdesk/"
ln -s /opt/gitdesk/gitdesk "$PKG/usr/bin/gitdesk"
cp packaging/gitdesk.png "$PKG/usr/share/icons/hicolor/256x256/apps/gitdesk.png"
cp packaging/linux/gitdesk.desktop "$PKG/usr/share/applications/gitdesk.desktop"
SIZE=$(du -sk "$PKG/opt" | cut -f1)
cat > "$PKG/DEBIAN/control" <<EOF
Package: gitdesk
Version: ${VERSION}
Section: devel
Priority: optional
Architecture: ${ARCH}
Depends: git, libxcb-cursor0, libegl1, libxkbcommon-x11-0, libfontconfig1
Recommends: git-lfs, fonts-noto-cjk
Installed-Size: ${SIZE}
Maintainer: GitDesk <noreply@example.com>
Description: GitDesk - graphical Git client (繁體中文 / English)
 Full-featured Git GUI: staging by hunk/line, commit graph, branches, merge,
 rebase (interactive), stash, tags, remotes, submodules, worktrees, bisect,
 blame, reflog, LFS, hooks and more. Auto-refreshes when the repository is
 changed by other tools.
EOF
cat > "$PKG/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q /usr/share/applications || true
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q -t /usr/share/icons/hicolor || true
exit 0
EOF
chmod 755 "$PKG/DEBIAN/postinst"
dpkg-deb --build --root-owner-group "$PKG" "dist/gitdesk_${VERSION}_${ARCH}.deb"

# ---------- portable tarball ----------
tar -C dist -czf "dist/GitDesk-${VERSION}-linux-x86_64.tar.gz" GitDesk
echo "Done:"
ls -lh dist/*.deb dist/*.tar.gz
