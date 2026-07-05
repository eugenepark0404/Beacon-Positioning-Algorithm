"""출력 스키마 — 트랙4 파이프라인/트랙2 입력과 호환되는 포맷 고정.

CSV 컬럼: timestamp,x,y,method,n_beacons,shadow_corrected,residual
JSON: {"positions": [ {...}, ... ], "meta": {...}}
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import List, Optional


@dataclass
class PositionRecord:
    timestamp: float
    x: float
    y: float
    method: str
    n_beacons: int
    shadow_corrected: bool = False
    residual: float = 0.0
    x_true: Optional[float] = None
    y_true: Optional[float] = None
    meta: dict = field(default_factory=dict)

    @property
    def error_m(self) -> Optional[float]:
        if self.x_true is None or self.y_true is None:
            return None
        return ((self.x - self.x_true) ** 2 + (self.y - self.y_true) ** 2) ** 0.5


FIELDS = ["timestamp", "x", "y", "method", "n_beacons", "shadow_corrected", "residual",
          "x_true", "y_true"]


def write_positions_csv(records: List[PositionRecord], path: str | Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(FIELDS)
        for r in records:
            d = asdict(r)
            w.writerow([d[k] for k in FIELDS])


def write_positions_json(records: List[PositionRecord], path: str | Path,
                         meta: Optional[dict] = None) -> None:
    payload = {"meta": meta or {}, "positions": [asdict(r) for r in records]}
    Path(path).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
