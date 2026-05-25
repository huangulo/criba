import logging

from lingua import Language, LanguageDetectorBuilder

from criba.filters.base import BaseFilter, FilterResult
from criba.models.raw_post import RawPost

logger = logging.getLogger(__name__)

_detector = None


def _get_detector():
    global _detector
    if _detector is None:
        _detector = (
            LanguageDetectorBuilder.from_languages(
                Language.SPANISH, Language.ENGLISH, Language.PORTUGUESE,
                Language.FRENCH, Language.GERMAN, Language.ITALIAN,
            )
            .with_minimum_relative_distance(0.25)
            .build()
        )
    return _detector


class LanguageFilter(BaseFilter):
    
    def __init__(self, primary_language: str = "es"):
        self._primary_language = primary_language
        self._iso_map = {
            "es": Language.SPANISH,
            "en": Language.ENGLISH,
            "pt": Language.PORTUGUESE,
            "fr": Language.FRENCH,
            "de": Language.GERMAN,
            "it": Language.ITALIAN,
        }
    
    def get_name(self) -> str:
        return "language"
    
    @property
    def weight(self) -> float:
        return 0.5
    
    async def apply(self, post: RawPost, context: dict) -> FilterResult:
        primary = context.get("primary_language", self._primary_language)
        
        if not post.content or len(post.content.strip()) < 20:
            return FilterResult(score=0.1, metadata={"language_detected": None})
        
        detector = _get_detector()
        detected = detector.detect_language_of(post.content)
        
        if detected is None:
            return FilterResult(score=0.1, metadata={"language_detected": None})
        
        detected_iso = detected.iso_code_639_1.name.lower()
        
        primary_lang = self._iso_map.get(primary)
        matches = detected == primary_lang if primary_lang else False
        
        score = 0.0 if matches else 0.3
        
        return FilterResult(
            score=score,
            flagged=not matches,
            metadata={
                "language_detected": detected_iso,
                "language_matches_primary": matches,
            },
        )
