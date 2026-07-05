"""BLE 비콘 실내·지하 측위 코어 패키지 (트랙1 산출물).

파이프라인: ingest → preprocessing → distance → positioning → correction → fusion → output
모든 수식의 출처는 docs/수식_유도서.md (P1~P9 태그)를 따른다.
"""
__version__ = "0.1.0"

from .pipeline import PositioningPipeline  # noqa: F401
