#!/bin/bash

set -e

PROJECT_ROOT="$(dirname "$(readlink -e "$0")")/../../.."
CONTRIB="$PROJECT_ROOT/contrib"
DISTDIR="$PROJECT_ROOT/dist"
BUILDDIR="$CONTRIB/build-linux/appimage/build/appimage"
APPDIR="$BUILDDIR/Electron-Fittexxcoin.AppDir"
CACHEDIR="$CONTRIB/build-linux/appimage/.cache/appimage"
PYDIR="$APPDIR"/usr/lib/python3.11

export GCC_STRIP_BINARIES="1"
export GIT_SUBMODULE_FLAGS="--recommend-shallow --depth 1"

# Newer git errors-out about permissions here sometimes, so do this
git config --global --add safe.directory $(readlink -f "$PROJECT_ROOT")

. "$CONTRIB"/base.sh

# pinned versions
PKG2APPIMAGE_COMMIT="eb8f3acdd9f11ab19b78f5cb15daa772367daf15"


VERSION=`git_describe_filtered`
APPIMAGE="$DISTDIR/Electron-Fittexxcoin-$VERSION-x86_64.AppImage"

rm -rf "$BUILDDIR"
mkdir -p "$APPDIR" "$CACHEDIR" "$DISTDIR"

info "downloading some dependencies."
download_if_not_exist "$CACHEDIR/functions.sh" "https://raw.githubusercontent.com/AppImage/pkg2appimage/$PKG2APPIMAGE_COMMIT/functions.sh"
verify_hash "$CACHEDIR/functions.sh" "78b7ee5a04ffb84ee1c93f0cb2900123773bc6709e5d1e43c37519f590f86918"

download_if_not_exist "$CACHEDIR/appimagetool" "https://github.com/AppImage/AppImageKit/releases/download/12/appimagetool-x86_64.AppImage"
verify_hash "$CACHEDIR/appimagetool" "d918b4df547b388ef253f3c9e7f6529ca81a885395c31f619d9aaf7030499a13"

download_if_not_exist "$CACHEDIR/Python-$PYTHON_VERSION.tar.xz" "https://www.python.org/ftp/python/$PYTHON_VERSION/Python-$PYTHON_VERSION.tar.xz"
verify_hash "$CACHEDIR/Python-$PYTHON_VERSION.tar.xz" $PYTHON_SRC_TARBALL_HASH

(
    cd "$PROJECT_ROOT"
    for pkg in secp zbar openssl libevent zlib tor ; do
        "$CONTRIB"/make_$pkg || fail "Could not build $pkg"
    done
)

info "Building Python"
tar xf "$CACHEDIR/Python-$PYTHON_VERSION.tar.xz" -C "$BUILDDIR"
(
    cd "$BUILDDIR/Python-$PYTHON_VERSION"
    LC_ALL=C export BUILD_DATE=$(date -u -d "@$SOURCE_DATE_EPOCH" "+%b %d %Y")
    LC_ALL=C export BUILD_TIME=$(date -u -d "@$SOURCE_DATE_EPOCH" "+%H:%M:%S")
    # Patch taken from Ubuntu http://archive.ubuntu.com/ubuntu/pool/main/p/python3.11/python3.11_3.11.6-3.debian.tar.xz
    patch -p1 < "$CONTRIB/build-linux/appimage/patches/python-3.11.6-reproducible-buildinfo.diff" || fail "Could not patch Python build system for reproducibility"
    ./configure \
      --cache-file="$CACHEDIR/python.config.cache" \
      --prefix="$APPDIR/usr" \
      --enable-ipv6 \
      --enable-shared \
      -q || fail "Python configure failed"
    make -j$WORKER_COUNT -s || fail "Could not build Python"
    make -s install > /dev/null || fail "Failed to install Python"
    # When building in docker on macOS, python builds with .exe extension because the
    # case insensitive file system of macOS leaks into docker. This causes the build
    # to result in a different output on macOS compared to Linux. We simply patch
    # sysconfigdata to remove the extension.
    # Some more info: https://bugs.python.org/issue27631
    sed -i -e 's/\.exe//g' "$PYDIR"/_sysconfigdata*
)

appdir_python() {
  env \
    PYTHONNOUSERSITE=1 \
    LD_LIBRARY_PATH="$APPDIR/usr/lib:$APPDIR/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH+:$LD_LIBRARY_PATH}" \
    "$APPDIR/usr/bin/python3.11" "$@"
}

python='appdir_python'


info "Installing pip"
"$python" -m ensurepip


info "Preparing electrum-locale"
(
    cd "$PROJECT_ROOT"

    pushd "$CONTRIB"/electrum-locale
    if ! which msgfmt > /dev/null 2>&1; then
        fail "Please install gettext"
    fi
    for i in ./locale/*; do
        dir="$PROJECT_ROOT/electroncash/$i/LC_MESSAGES"
        mkdir -p $dir
        msgfmt --output-file="$dir/electron-fittexxcoin.mo" "$i/electron-fittexxcoin.po" || true
    done
    popd
)


function filter_deps {
  awk "$1"' {exclude=1; next} exclude && /^[[:space:]]/ {next} {exclude=0} !exclude {print}'
}

export CMAKE_PREFIX_PATH=$APPDIR/usr

info "Installing Electron Cash and its dependencies"
mkdir -p "$CACHEDIR/pip_cache"
# Note: We must specify -g0 for CFLAGS to ensure no debug symbols (which can be non-deterministic due to tmp paths
# encoded in the debug symbols).
CFLAGS="-g0" "$python" -m pip install --no-deps --no-warn-script-location --no-binary :all: --cache-dir "$CACHEDIR/pip_cache" -r "$CONTRIB/deterministic-build/requirements-pip.txt"
CFLAGS="-g0" "$python" -m pip install --no-deps --no-warn-script-location --no-binary :all: --cache-dir "$CACHEDIR/pip_cache" -r "$CONTRIB/deterministic-build/requirements-build-appimage.txt"
CFLAGS="-g0" "$python" -m pip install --no-deps --no-warn-script-location --no-binary :all: --cache-dir "$CACHEDIR/pip_cache" -r "$CONTRIB/deterministic-build/requirements.txt"
CFLAGS="-g0" "$python" -m pip install --no-deps --no-warn-script-location --no-binary :all: --only-binary PyQt5,PyQt5-Qt5 --cache-dir "$CACHEDIR/pip_cache" -r <(filter_deps /zxing-cpp/ < "$CONTRIB/deterministic-build/requirements-binaries.txt")
# zxing-cpp 2.2.1 with patch for reproducible build, see https://github.com/zxing-cpp/zxing-cpp/pull/730
CFLAGS="-g0" "$python" -m pip install --no-deps --no-warn-script-location --no-binary :all: --only-binary cmake --cache-dir "$CACHEDIR/pip_cache" git+https://github.com/EchterAgo/zxing-cpp.git@3ac618250672db83e7a37b4e43fe6f72b88756d4#subdirectory=wrappers/python
# Temporary fix for hidapi incompatibility with Cython 3
# See https://github.com/trezor/cython-hidapi/issues/155
# We use PIP_CONSTRAINT as an environment variable instead of command line flag because it gets passed to subprocesses
# like the isolated build environment pip uses for dependencies.
PIP_CONSTRAINT="$CONTRIB/requirements/build-constraint.txt" CFLAGS="-g0" "$python" -m pip install --no-deps --no-warn-script-location --no-binary :all: --cache-dir "$CACHEDIR/pip_cache" -r "$CONTRIB/deterministic-build/requirements-hw.txt"
CFLAGS="-g0" "$python" -m pip install --no-deps --no-warn-script-location --cache-dir "$CACHEDIR/pip_cache" "$PROJECT_ROOT"
"$python" -m pip uninstall -y -r "$CONTRIB/requirements/requirements-build-uninstall.txt"


info "Copying desktop integration"
cp -fp "$PROJECT_ROOT/electron-fittexxcoin.desktop" "$APPDIR/electron-fittexxcoin.desktop"
cp -fp "$PROJECT_ROOT/icons/electron-fittexxcoin.png" "$APPDIR/electron-fittexxcoin.png"


# add launcher
info "Adding launcher"
cp -fp "$CONTRIB/build-linux/appimage/scripts/common.sh" "$APPDIR/common.sh" || fail "Could not copy python script"
cp -fp "$CONTRIB/build-linux/appimage/scripts/apprun.sh" "$APPDIR/AppRun" || fail "Could not copy AppRun script"
cp -fp "$CONTRIB/build-linux/appimage/scripts/python.sh" "$APPDIR/python" || fail "Could not copy python script"

info "Finalizing AppDir"
(
    export PKG2AICOMMIT="$PKG2APPIMAGE_COMMIT"
    . "$CACHEDIR/functions.sh"

    cd "$APPDIR"
    # copy system dependencies
    copy_deps
    move_lib

    # apply global appimage blacklist to exclude stuff
    # move usr/include out of the way to preserve usr/include/python3.11m.
    mv usr/include usr/include.tmp
    delete_blacklisted
    mv usr/include.tmp usr/include
) || fail "Could not finalize AppDir"

# We copy some libraries here that are on the AppImage excludelist
info "Copying additional libraries"

# On some systems it can cause problems to use the system libusb
cp -fp /usr/lib/x86_64-linux-gnu/libusb-1.0.so "$APPDIR"/usr/lib/x86_64-linux-gnu/. || fail "Could not copy libusb"

# some distros lack libxkbcommon-x11
cp -f /usr/lib/x86_64-linux-gnu/libxkbcommon-x11.so.0 "$APPDIR"/usr/lib/x86_64-linux-gnu || fail "Could not copy libxkbcommon-x11"

# some distros lack some libxcb libraries (see #2189, #2196)
cp -f /usr/lib/x86_64-linux-gnu/libxcb* "$APPDIR"/usr/lib/x86_64-linux-gnu || fail "Could not copy libxkcb"

# we need to exclude the glib libraries, otherwise we can end up using multiple incompatible versions
# See https://github.com/AppImageCommunity/pkg2appimage/pull/500#issuecomment-1057287738
for name in module thread ; do
    rm -f "$APPDIR"/usr/lib/x86_64-linux-gnu/libg${name}-2.0.so.0 || fail "Could not remove libg${name}-2.0"
done

info "Stripping binaries of debug symbols"
# "-R .note.gnu.build-id" also strips the build id
# "-R .comment" also strips the GCC version information
strip_binaries()
{
  chmod u+w -R "$APPDIR"
  {
    printf '%s\0' "$APPDIR/usr/bin/python3.11"
    find "$APPDIR" -type f -regex '.*\.so\(\.[0-9.]+\)?$' -print0
  } | xargs -0 --no-run-if-empty --verbose strip -R .note.gnu.build-id -R .comment
}
strip_binaries

remove_emptydirs()
{
  find "$APPDIR" -type d -empty -print0 | xargs -0 --no-run-if-empty rmdir -vp --ignore-fail-on-non-empty
}
remove_emptydirs


info "Removing some unneeded files to decrease binary size"
rm -rf "$APPDIR"/usr/{share,include}
rm -rf "$PYDIR"/{test,ensurepip,lib2to3,idlelib,turtledemo}
rm -rf "$PYDIR"/{ctypes,sqlite3,tkinter,unittest}/test
rm -rf "$PYDIR"/distutils/{command,tests}
rm -rf "$PYDIR"/config-3.8-x86_64-linux-gnu
rm -rf "$PYDIR"/site-packages/Cryptodome/SelfTest
rm -rf "$PYDIR"/site-packages/{psutil,qrcode}/tests
for component in connectivity declarative location multimedia quickcontrols quickcontrols2 serialport webengine websockets xmlpatterns ; do
  rm -rf "$PYDIR"/site-packages/PyQt5/Qt/translations/qt${component}_*
done
rm -rf "$PYDIR"/site-packages/PyQt5/Qt/{qml,libexec,qsci}
rm -rf "$PYDIR"/site-packages/PyQt5/{pyrcc.so,pylupdate.so,uic,bindings}
rm -rf "$PYDIR"/site-packages/PyQt5/Qt/plugins/{assetimporters,bearer,gamepads,geometryloaders,geoservices,playlistformats,position,printsupport,renderplugins,sceneparsers,sensors,sqldrivers,texttospeech,webview}
for component in Bluetooth Concurrent Designer Help Location NetworkAuth Nfc Positioning PositioningQuick PrintSupport Qml Quick RemoteObjects Sensors SerialPort Sql Test TextToSpeech Web Xml ; do

    rm -rf "$PYDIR"/site-packages/PyQt5/Qt/lib/libQt5${component}*
    rm -rf "$PYDIR"/site-packages/PyQt5/Qt${component}*
done
rm -rf "$PYDIR"/site-packages/PyQt5/Qt.*

# these are deleted as they were not deterministic; and are not needed anyway
find "$APPDIR" -path '*/__pycache__*' -delete
rm -rf "$PYDIR"/site-packages/*.dist-info/
rm -rf "$PYDIR"/site-packages/*.egg-info/


find -exec touch -h -d '2000-11-11T11:11:11+00:00' {} +


info "Creating the AppImage"
(
    cd "$BUILDDIR"
    cp "$CACHEDIR/appimagetool" "$CACHEDIR/appimagetool_copy"
    # zero out "appimage" magic bytes, as on some systems they confuse the linker
    sed -i 's|AI\x02|\x00\x00\x00|' "$CACHEDIR/appimagetool_copy"
    chmod +x "$CACHEDIR/appimagetool_copy"
    "$CACHEDIR/appimagetool_copy" --appimage-extract
    # We build a small wrapper for mksquashfs that removes the -mkfs-fixed-time option
    # that mksquashfs from squashfskit does not support. It is not needed for squashfskit.
    cat > ./squashfs-root/usr/lib/appimagekit/mksquashfs << EOF
#!/bin/sh
args=\$(echo "\$@" | sed -e 's/-mkfs-fixed-time 0//')
mksquashfs \$args
EOF
    env VERSION="$VERSION" ARCH=x86_64 SOURCE_DATE_EPOCH=1530212462 \
                ./squashfs-root/AppRun --no-appstream --verbose "$APPDIR" "$APPIMAGE" \
                || fail "AppRun failed"
) || fail "Could not create the AppImage"


info "Done"
ls -la "$DISTDIR"
sha256sum "$DISTDIR"/*
