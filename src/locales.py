from loguru import logger
import json
import os
from typing import Optional, Any
import string

class SafeFormatter(string.Formatter):
    def get_value(self, key, args, kwargs):
        if isinstance(key, str):
            return kwargs.get(key, '{' + key + '}')
        else:
            return string.Formatter.get_value(self, key, args, kwargs)

class Localization:
    def __init__(self, default_locale: str = 'en'):
        self.default_locale = default_locale
        self.translations: dict[str, dict[str, Any]] = {}
        self.formatter = SafeFormatter()
        self.load_translations(default_locale)

    def load_translations(self, locale: str):
        # 指定された言語の翻訳ファイルを読み込む
        locale_file = os.path.join('loc', f'{locale}.json')
        if os.path.exists(locale_file):
            with open(locale_file, 'r', encoding='utf-8') as f:
                self.translations[locale] = json.load(f)
        else:
            # 翻訳ファイルが存在しない場合は空の辞書を設定
            self.translations[locale] = {}

    def __getattr__(self, key: str):
        # 属性アクセスでキーを取得
        return LocalizationDict(self, [key])

    def get_translation(self, keys: list[str], locale: str, **kwargs):
        # 翻訳を取得します
        if locale not in self.translations:
            self.load_translations(locale)
        translation: Any = self.translations.get(locale, {})
        for k in keys:
            if isinstance(translation, dict):
                translation = translation.get(k)
            else:
                translation = None
            if translation is None:
                break
        if translation is None and locale != 'en':
            # 翻訳が見つからない場合、デフォルトの'en'で再試行
            return self.get_translation(keys, 'en', **kwargs)
        if translation is not None and isinstance(translation, str):
            used_keys = {field_name for _, field_name, _, _ in self.formatter.parse(translation) if field_name}
            unused_keys = {key: value for key, value in kwargs.items() if key not in used_keys}
            if unused_keys:
                # 不必要なキーがある場合はログに出力
                logger.debug(f"Unused keys in translation: {unused_keys}")
            return self.formatter.format(translation, **kwargs)
        return '.'.join(keys)

class LocalizationDict:
    def __init__(self, localization: Localization, keys: list[str]):
        self.localization = localization
        self.keys = keys

    def __getattr__(self, key: str):
        # 次のキーを追加して新しいLocalizationDictを返す
        return LocalizationDict(self.localization, self.keys + [key])

    def __call__(self, locale: Optional[str] = None, **kwargs):
        # 指定された言語で翻訳を取得
        if locale is None:
            locale = self.localization.default_locale
        return self.localization.get_translation(self.keys, locale, **kwargs)
