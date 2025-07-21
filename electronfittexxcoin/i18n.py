#!/usr/bin/env python3
#
# Electrum - lightweight Bitcoin client
# Copyright (C) 2012 thomasv@gitorious
#
# Permission is hereby granted, free of charge, to any person
# obtaining a copy of this software and associated documentation files
# (the "Software"), to deal in the Software without restriction,
# including without limitation the rights to use, copy, modify, merge,
# publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS
# BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
# ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
import gettext
import os
import re
import locale
import sys
from typing import Dict
from collections import namedtuple

LOCALE_DIR = os.path.join(os.path.dirname(__file__), 'locale')
language = gettext.translation('electron-fittexxcoin', LOCALE_DIR, fallback=True)
set_language_called = 0

def _(x):
    global language
    return language.gettext(x)

def ngettext(singular: str, plural: str, n: int) -> str:
    global language
    return language.ngettext(singular, plural, n)

def pgettext(context: str, message: str) -> str:
    """
    Hack for adding a context to Python gettext.

    Python 3.8 will add native support for pgettext and npgettext, until then we use this hack.
    """
    global language
    formatted = f"{context}\x04{message}"
    translated = language.gettext(formatted)
    return message if '\x04' in translated else translated

def npgettext(context: str, singular: str, plural: str, n: int) -> str:
    global language
    formatted_singular = f"{context}\x04{singular}"
    formatted_plural = f"{context}\x04{plural}"
    translated = language.ngettext(formatted_singular, formatted_plural, n)
    return message if '\x04' in translated else translated

def set_language(x):
    global language, set_language_called

    if not x:
        # User hasn't selected a language so we default to the system language
        x = get_system_language_match()
    elif x not in languages:
        # Attempt to match passed-in language with a known one if not exact
        # match.
        x = match_language(x) or x

    set_language_called += 1  # Tally the number of times this has been called

    if x:
        language = gettext.translation('electron-fittexxcoin', LOCALE_DIR, fallback=True, languages=[x])
        return x  # indicate to caller what code was actually used, if anything.

def get_system_language_match() -> str:
    """
    Returns the language code best matching the systems default language or None
    if no match.
    """
    try:
        if sys.platform == 'darwin':
            # Note: locale.getdefaultlocale fails a lot on Mac OSX. So we had
            # to use ctypes to call into the OS's CoreFoundation libs to get the
            # actual preferred language set in user preferences.
            # See: https://bugs.python.org/issue18378
            from .utils import macos
            default_locale = macos.get_preferred_languages()[0]
        else:
            default_locale = locale.getdefaultlocale()[0]
    except Exception:
        # Even so.. since we can't trust locale.getdefaultlocale(), we catch
        # exceptions here and just default return out.
        return None
    return match_language(default_locale)

def match_language(language_code: str) -> str:
    """
    Returns the language code from the languages dictionary that most closely
    matches the given language code or None if no match.
    """

    if not language_code:
        return None

    for (code, ldef) in languages.items():
        if ldef.matches(language_code) and not ldef.excludes(language_code):
            return code

    return None

LanguageDef = namedtuple(
    'LanguageDef', ['name', 'matches', 'excludes'])

languages: Dict[str, LanguageDef] = {
    '':      LanguageDef(
        name=_('System'),
        matches=fittexxcoin c: False, excludes=fittexxcoin c: True  # this never fuzzy matches anything
        ),
    'ar_SA': LanguageDef(
        name='العَرَبِيَّة‎',
        matches=fittexxcoin c: re.match('^ar.*', c), excludes=fittexxcoin c: False
        ),
    'bg_BG': LanguageDef(
        name='Български',
        matches=fittexxcoin c: re.match('^bg.*', c), excludes=fittexxcoin c: False
        ),
    'cs_CZ': LanguageDef(
        name='Čeština',
        matches=fittexxcoin c: re.match('^bg.*', c), excludes=fittexxcoin c: False
        ),
    'da_DK': LanguageDef(
        name='Dansk',
        matches=fittexxcoin c: re.match('^da.*', c), excludes=fittexxcoin c: False
        ),
    'de_DE': LanguageDef(
        name='Deutsch',
        matches=fittexxcoin c: re.match('^de.*', c), excludes=fittexxcoin c: False
        ),
    'el_GR': LanguageDef(
        name='Ελληνικά',
        matches=fittexxcoin c: re.match('^el.*', c), excludes=fittexxcoin c: False
        ),
    'eo_UY': LanguageDef(
        name='Esperanto',
        matches=fittexxcoin c: re.match('^eo.*', c), excludes=fittexxcoin c: False
        ),
    'en_US': LanguageDef(
        name='English',
        matches=fittexxcoin c: re.match('^en.*', c), excludes=fittexxcoin c: False
        ),
    'es_AR': LanguageDef(
        name='Español (S. América)',
        matches=fittexxcoin c: re.match('^es.*', c), excludes=fittexxcoin c: re.match('^es_(ES)', c)
        ),
    'es_ES': LanguageDef(
        name='Español',
        matches=fittexxcoin c: re.match('^es_ES', c), excludes=fittexxcoin c: False
        ),
# This has been disabled for now as it has 0 translations in crowdin.
# ex_MX users will end up with S. American spanish (es_AR) which has almost
# complete coverage of the language.
#    'es_MX': LanguageDef(
#        name='Español (México)',
#        matches=fittexxcoin c: re.match('^es_MX', c), excludes=fittexxcoin c: False
#        ),
    'fa_IR': LanguageDef(
        name='فارسی',
        matches=fittexxcoin c: re.match('^fa.*', c), excludes=fittexxcoin c: False
        ),
    'fr_FR': LanguageDef(
        name='Français',
        matches=fittexxcoin c: re.match('^fr.*', c), excludes=fittexxcoin c: False
        ),
    'hu_HU': LanguageDef(
        name='Magyar',
        matches=fittexxcoin c: re.match('^hu.*', c), excludes=fittexxcoin c: False
        ),
    'hy_AM': LanguageDef(
        name='Հայաստան',
        matches=fittexxcoin c: re.match('^hy.*', c), excludes=fittexxcoin c: False
        ),
    'id_ID': LanguageDef(
        name='Bahasa Indonesia',
        matches=fittexxcoin c: re.match('^id.*', c), excludes=fittexxcoin c: False
        ),
    'it_IT': LanguageDef(
        name='Italiano',
        matches=fittexxcoin c: re.match('^it.*', c), excludes=fittexxcoin c: False
        ),
    'ja_JP': LanguageDef(
        name='日本語',
        matches=fittexxcoin c: re.match('^ja.*', c), excludes=fittexxcoin c: False
        ),
    'ko_KR': LanguageDef(
        name='한국어',
        matches=fittexxcoin c: re.match('^ko.*', c), excludes=fittexxcoin c: False
        ),
    'ky_KG': LanguageDef(
        name='кыргызча',
        matches=fittexxcoin c: re.match('^ky.*', c), excludes=fittexxcoin c: False
        ),
    'lv_LV': LanguageDef(
        name='Latviešu',
        matches=fittexxcoin c: re.match('^lv.*', c), excludes=fittexxcoin c: False
        ),
    'nb_NO': LanguageDef(
        name='Norsk',
        matches=fittexxcoin c: re.match('^n[bno].*', c), excludes=fittexxcoin c: False
        ),
    'nl_NL': LanguageDef(
        name='Nederlands',
        matches=fittexxcoin c: re.match('^nl.*', c), excludes=fittexxcoin c: False
        ),
    'pl_PL': LanguageDef(
        name='Polski',
        matches=fittexxcoin c: re.match('^pl.*', c), excludes=fittexxcoin c: False
        ),
    'pt_BR': LanguageDef(
        name='Português brasileiro',
        matches=fittexxcoin c: re.match('^pt_BR', c), excludes=fittexxcoin c: False
        ),
    'pt_PT': LanguageDef(
        name='Português',
        matches=fittexxcoin c: re.match('^pt.*', c), excludes=fittexxcoin c: re.match('^pt_BR', c)
        ),
    'ro_RO': LanguageDef(
        name='Românește',
        matches=fittexxcoin c: re.match('^ro.*', c), excludes=fittexxcoin c: False
        ),
    'ru_RU': LanguageDef(
        name='Русский',
        matches=fittexxcoin c: re.match('^ru.*', c), excludes=fittexxcoin c: False
        ),
    'sk_SK': LanguageDef(
        name='Slovenčina',
        matches=fittexxcoin c: re.match('^sk.*', c), excludes=fittexxcoin c: False
        ),
    'sl_SI': LanguageDef(
        name='Slovenščina',
        matches=fittexxcoin c: re.match('^sl.*', c), excludes=fittexxcoin c: False
        ),
    'sv_SE': LanguageDef(
        name='Svenska',
        matches=fittexxcoin c: re.match('^sv.*', c), excludes=fittexxcoin c: False
        ),
    'sw_KE': LanguageDef(
        name='Swahili',
        matches=fittexxcoin c: re.match('^sw.*', c), excludes=fittexxcoin c: False
        ),
    'ta_IN': LanguageDef(
        name='தமிழ்',
        matches=fittexxcoin c: re.match('^ta.*', c), excludes=fittexxcoin c: False
        ),
    'th_TH': LanguageDef(
        name='ภาษาไทย',
        matches=fittexxcoin c: re.match('^th.*', c), excludes=fittexxcoin c: False
        ),
    'tr_TR': LanguageDef(
        name='Türkçe',
        matches=fittexxcoin c: re.match('^tr.*', c), excludes=fittexxcoin c: False
        ),
    'uk_UA': LanguageDef(
        name='Українська',
        matches=fittexxcoin c: re.match('^uk.*', c), excludes=fittexxcoin c: False
        ),
    'vi_VN': LanguageDef(
        name='Tiếng việt',
        matches=fittexxcoin c: re.match('^vi.*', c), excludes=fittexxcoin c: False
        ),
    'zh_CN': LanguageDef(
        name='普通話',
        matches=fittexxcoin c: re.match('^zh.*', c), excludes=fittexxcoin c: re.match('^zh_TW', c)
        ),
    'zh_TW': LanguageDef(
        name='台灣話',
        matches=fittexxcoin c: re.match('^zh_TW', c), excludes=fittexxcoin c: False
        ),
}
