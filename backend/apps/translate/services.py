import hashlib
import logging
import os
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

_CACHE_HOURS = getattr(settings, 'DEEPL_CACHE_HOURS', 720)


def _cache_key(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def translate(text: str, source_lang: str = 'KO', target_lang: str = 'JA') -> str:
    """DeepL로 번역. DB 캐시 적용 (기본 30일)."""
    if not text or not text.strip():
        return text

    from .models import TranslationCache

    # 캐시 조회 (같은 원문 + 언어쌍, 유효기간 내)
    cutoff = timezone.now() - timedelta(hours=_CACHE_HOURS)
    cached = TranslationCache.objects.filter(
        source_lang=source_lang,
        target_lang=target_lang,
        source_text=text,
        created_at__gte=cutoff,
    ).first()
    if cached:
        return cached.translated_text

    api_key = getattr(settings, 'DEEPL_API_KEY', '') or os.environ.get('DEEPL_API_KEY', '')
    if not api_key:
        logger.warning("DEEPL_API_KEY not set — returning original text")
        return text

    try:
        import deepl
        translator = deepl.Translator(api_key)
        result = translator.translate_text(text, source_lang=source_lang, target_lang=target_lang)
        translated = result.text
    except Exception as e:
        logger.error("DeepL translation failed: %s", e)
        return text

    TranslationCache.objects.create(
        source_lang=source_lang,
        target_lang=target_lang,
        source_text=text,
        translated_text=translated,
    )
    return translated


def translate_bulk(texts: list[str], source_lang: str = 'KO', target_lang: str = 'JA') -> list[str]:
    """여러 텍스트 일괄 번역. 캐시 히트 항목은 API 호출 생략."""
    if not texts:
        return []

    from .models import TranslationCache

    cutoff = timezone.now() - timedelta(hours=_CACHE_HOURS)
    results = [''] * len(texts)
    uncached_indices = []
    uncached_texts = []

    for i, text in enumerate(texts):
        if not text or not text.strip():
            results[i] = text
            continue
        cached = TranslationCache.objects.filter(
            source_lang=source_lang,
            target_lang=target_lang,
            source_text=text,
            created_at__gte=cutoff,
        ).first()
        if cached:
            results[i] = cached.translated_text
        else:
            uncached_indices.append(i)
            uncached_texts.append(text)

    if not uncached_texts:
        return results

    api_key = getattr(settings, 'DEEPL_API_KEY', '') or os.environ.get('DEEPL_API_KEY', '')
    if not api_key:
        for i, text in zip(uncached_indices, uncached_texts):
            results[i] = text
        return results

    try:
        import deepl
        translator = deepl.Translator(api_key)
        translated_list = translator.translate_text(uncached_texts, source_lang=source_lang, target_lang=target_lang)
        for i, (idx, src, res) in enumerate(zip(uncached_indices, uncached_texts, translated_list)):
            results[idx] = res.text
            TranslationCache.objects.create(
                source_lang=source_lang,
                target_lang=target_lang,
                source_text=src,
                translated_text=res.text,
            )
    except Exception as e:
        logger.error("DeepL bulk translation failed: %s", e)
        for i, text in zip(uncached_indices, uncached_texts):
            results[i] = text

    return results
