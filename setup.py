#!/usr/bin/env python3

# python setup.py sdist --format=zip,gztar

from setuptools import setup
import setuptools.command.sdist
import os
import sys
import platform
import importlib.util
import argparse

with open('contrib/requirements/requirements.txt') as f:
    requirements = f.read().splitlines()

with open('contrib/requirements/requirements-hw.txt') as f:
    requirements_hw = f.read().splitlines()

with open('contrib/requirements/requirements-binaries.txt') as f:
    requirements_binaries = f.read().splitlines()

def load_source(module_name, module_path):
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

version = load_source('version', 'electronfittexxcoin/version.py')

if sys.version_info[:3] < (3, 8):
    sys.exit("Error: Electron Cash requires Python version >= 3.8...")

data_files = []

if platform.system() in ['Linux', 'FreeBSD', 'DragonFly']:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--user', dest='is_user', action='store_true', default=False)
    parser.add_argument('--system', dest='is_user', action='store_false', default=False)
    parser.add_argument('--root=', dest='root_path', metavar='dir', default='/')
    parser.add_argument('--prefix=', dest='prefix_path', metavar='prefix', nargs='?', const='/', default=sys.prefix)
    opts, _ = parser.parse_known_args(sys.argv[1:])

    # Use per-user */share directory if the global one is not writable or if a per-user installation
    # is attempted
    user_share   = os.environ.get('XDG_DATA_HOME', os.path.expanduser('~/.local/share'))
    system_share = os.path.join(opts.prefix_path, "share")
    if not opts.is_user:
        # Not neccarily a per-user installation try system directories
        if os.access(opts.root_path + system_share, os.W_OK):
            # Global /usr/share is writable for us – so just use that
            share_dir = system_share
        elif not os.path.exists(opts.root_path + system_share) and os.access(opts.root_path, os.W_OK):
            # Global /usr/share does not exist, but / is writable – keep using the global directory
            # (happens during packaging)
            share_dir = system_share
        else:
            # Neither /usr/share (nor / if /usr/share doesn't exist) is writable, use the
            # per-user */share directory
            share_dir = user_share
    else:
        # Per-user installation
        share_dir = user_share
    data_files += [
        # Menu icon
        (os.path.join(share_dir, 'icons/hicolor/256x256/apps/'),   ['icons/electron-fittexxcoin.png']),
        (os.path.join(share_dir, 'pixmaps/'),                      ['icons/electron-fittexxcoin.png']),
        (os.path.join(share_dir, 'icons/hicolor/scalable/apps/'),  ['icons/electron-fittexxcoin.svg']),
        # Menu entry
        (os.path.join(share_dir, 'applications/'), ['electron-fittexxcoin.desktop']),
        # App stream (store) metadata
        (os.path.join(share_dir, 'metainfo/'), ['org.electronfittexxcoin.FittexxcoinCash.appdata.xml']),
    ]

class MakeAllBeforeSdist(setuptools.command.sdist.sdist):
    """Does some custom stuff before calling super().run()."""

    user_options = setuptools.command.sdist.sdist.user_options + [
        ("disable-secp", None, "Disable libsecp256k1 complilation (default)."),
        ("enable-secp", None, "Enable libsecp256k1 complilation."),
        ("disable-zbar", None, "Disable libzbar complilation (default)."),
        ("enable-zbar", None, "Enable libzbar complilation."),
        ("disable-tor", None, "Disable tor complilation (default)."),
        ("enable-tor", None, "Enable tor complilation.")
    ]

    def initialize_options(self):
        self.disable_secp = None
        self.enable_secp = None
        self.disable_zbar = None
        self.enable_zbar = None
        self.disable_tor = None
        self.enable_tor = None
        super().initialize_options()

    def finalize_options(self):
        if self.enable_secp is None:
            self.enable_secp = False
        self.enable_secp = not self.disable_secp and self.enable_secp
        if self.enable_zbar is None:
            self.enable_zbar = False
        self.enable_zbar = not self.disable_zbar and self.enable_zbar
        if self.enable_tor is None:
            self.enable_tor = False
        self.enable_tor = not self.disable_tor and self.enable_tor
        super().finalize_options()

    def run(self):
        """Run command."""
        #self.announce("Running make_locale...")
        #0==os.system("contrib/make_locale") or sys.exit("Could not make locale, aborting")
        #self.announce("Running make_packages...")
        #0==os.system("contrib/make_packages") or sys.exit("Could not make locale, aborting")
        if self.enable_secp:
            self.announce("Running make_secp...")
            0==os.system("contrib/make_secp") or sys.exit("Could not build libsecp256k1")
        if self.enable_zbar:
            self.announce("Running make_zbar...")
            0==os.system("contrib/make_zbar") or sys.exit("Could not build libzbar")
        if self.enable_tor:
            self.announce("Running make_openssl...")
            0==os.system("contrib/make_openssl") or sys.exit("Could not build openssl")
            self.announce("Running make_libevent...")
            0==os.system("contrib/make_libevent") or sys.exit("Could not build libevent")
            self.announce("Running make_zlib...")
            0==os.system("contrib/make_zlib") or sys.exit("Could not build zlib")
            self.announce("Running make_tor...")
            0==os.system("contrib/make_tor") or sys.exit("Could not build tor")
        super().run()


platform_package_data = {
    'electronfittexxcoin_gui.qt': [],
}

if sys.platform in ('linux'):
    platform_package_data['electronfittexxcoin_gui.qt'] += [
            'data/ecsupplemental_lnx.ttf',
            'data/fonts.xml'
    ]

if sys.platform in ('win32', 'cygwin'):
    platform_package_data['electronfittexxcoin_gui.qt'] += [
            'data/ecsupplemental_win.ttf'
    ]

setup(
    cmdclass={
        'sdist': MakeAllBeforeSdist,
    },
    name=os.environ.get('EC_PACKAGE_NAME') or "Electron Cash",
    version=os.environ.get('EC_PACKAGE_VERSION') or version.PACKAGE_VERSION,
    install_requires=requirements,
    extras_require={
        'hardware': requirements_hw,
        'gui': requirements_binaries,
        'console2': ['ipython', 'qtconsole'],  # For optional --console2 support in Qt GUI
        'all': requirements_hw + requirements_binaries,
    },
    packages=[
        'electronfittexxcoin',
        'electronfittexxcoin.qrreaders',
        'electronfittexxcoin.slp',
        'electronfittexxcoin.rpa',
        'electronfittexxcoin.tor',
        'electronfittexxcoin.utils',
        'electronfittexxcoin_gui',
        'electronfittexxcoin_gui.qt',
        'electronfittexxcoin_gui.qt.qrreader',
        'electronfittexxcoin_gui.qt.utils',
        'electronfittexxcoin_gui.qt.utils.darkdetect',
        'electronfittexxcoin_plugins',
        'electronfittexxcoin_plugins.audio_modem',
        'electronfittexxcoin_plugins.cosigner_pool',
        'electronfittexxcoin_plugins.email_requests',
        'electronfittexxcoin_plugins.hw_wallet',
        'electronfittexxcoin_plugins.keepkey',
        'electronfittexxcoin_plugins.ledger',
        'electronfittexxcoin_plugins.trezor',
        'electronfittexxcoin_plugins.digitalbitbox',
        'electronfittexxcoin_plugins.virtualkeyboard',
        'electronfittexxcoin_plugins.shuffle_deprecated',
        'electronfittexxcoin_plugins.satochip',
        'electronfittexxcoin_plugins.fusion',
    ],
    package_data={
        'electronfittexxcoin': [
            'servers.json',
            'servers_testnet.json',
            'servers_testnet4.json',
            'servers_scalenet.json',
            'servers_regtest.json',
            'servers_chipnet.json',
            'currencies.json',
            'www/index.html',
            'wordlist/*.txt',
            'libsecp256k1*',
            'libzbar*',
            'locale/*/LC_MESSAGES/electron-fittexxcoin.mo',
            'tor/bin/*'
        ],
        'electronfittexxcoin_plugins.shuffle_deprecated': [
            'servers.json'
        ],
        'electronfittexxcoin_plugins.fusion': [
            '*.svg', '*.png'
        ],
        # On Linux and Windows this means adding electronfittexxcoin_gui/qt/data/*.ttf
        # On Darwin we don't use that font, so we don't add it to save space.
        **platform_package_data
    },
    scripts=['electron-fittexxcoin'],
    data_files=data_files,
    description="Lightweight Fittexxcoin Wallet",
    author="The Fittexxcoin core Developers",
    author_email="sylondata25@gmail.com",
    license="MIT Licence",
    url="http://fittexxcoinblockchain.com",
    long_description="""Lightweight fittexxcoin Wallet"""
)
