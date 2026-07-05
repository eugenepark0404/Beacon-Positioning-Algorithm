"""Fuzzy Type-1/Type-2 가중 핑거프린팅 — P9 (Sensors 19(9):2114, 2019) §2.2.

P9 Eq.(5): Dᵢ = sqrt( Σⱼ ((Pᵢⱼ − P'ⱼ)·wᵢⱼ)² )
  — 비콘 j별 가중 wᵢⱼ를 퍼지 추론(FIS)으로 부여한 가중 유클리드 거리
    (마할라노비스 거리와 유사하되 공분산 대신 FIS, P9 §2.2.2).
P9 Eq.(4): 좌표 = 상위 k 참조점의 w-가중 평균 (WKNN).
FIS 구조 (P9 §2.2.2-2.2.3): 삼각 멤버십 함수, Mamdani max-min, 무게중심 역퍼지화.
Type-2: 상/하 삼각 MF(hesitant fuzzy set) 결과의 구간 축약 (P9 §2.2.3).

정직성 주석: P9의 MF 절점·규칙표 수치는 본문 그림/부록(이미지)에 있어 정확히
추출 불가. P9 스스로 "값과 형태는 휴리스틱하게 선택"(§2.2.2)이라 밝혔으므로,
여기 절점도 P9의 도메인 정의(거리 0~10 m, RSSI −90~−20, 가중 0~1)를 따르되
휴리스틱 기본값이며 전부 생성자 인자로 교체 가능하다.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from .estimators import FingerprintDB, PositionEstimate, MISSING_RSSI


def _tri(x: float, a: float, b: float, c: float) -> float:
    """삼각 멤버십 함수 (P9: triangular membership)."""
    if x <= a or x >= c:
        return 1.0 if (x == a == b or x == c == b) else 0.0
    return (x - a) / (b - a) if x < b else (c - x) / (c - b)


class _Mamdani:
    """2입력(기하거리, RSSI) → 1출력(가중) Mamdani max-min + 무게중심 역퍼지화."""

    def __init__(self, spread: float = 0.0) -> None:
        s = spread  # Type-2: 상/하 MF 간격 (0이면 Type-1)
        # 도메인: 거리 0~10 m, RSSI −90~−20, 가중 0~1 (P9 §2.2.2 명시 도메인)
        self.dist_mfs = {
            "near": (0.0 - s, 0.0, 5.0 + s),
            "mid": (0.0 - s, 5.0, 10.0 + s),
            "far": (5.0 - s, 10.0, 10.0 + s),
        }
        self.rssi_mfs = {
            "weak": (-90.0 - s, -90.0, -55.0 + s),
            "med": (-90.0 - s, -55.0, -20.0 + s),
            "strong": (-55.0 - s, -20.0, -20.0 + s),
        }
        self.weight_mfs = {
            "low": (0.0, 0.0, 0.5),
            "med": (0.0, 0.5, 1.0),
            "high": (0.5, 1.0, 1.0),
        }
        # 규칙표 (P9 부록 구조를 따른 휴리스틱: 가깝고 강하면 신뢰↑)
        self.rules: List[Tuple[str, str, str]] = [
            ("near", "strong", "high"), ("near", "med", "high"), ("near", "weak", "med"),
            ("mid", "strong", "high"), ("mid", "med", "med"), ("mid", "weak", "low"),
            ("far", "strong", "med"), ("far", "med", "low"), ("far", "weak", "low"),
        ]

    def infer(self, dist_m: float, rssi: float) -> float:
        ys = np.linspace(0.0, 1.0, 101)
        agg = np.zeros_like(ys)
        for dn, rn, wn in self.rules:
            fire = min(_tri(dist_m, *self.dist_mfs[dn]),
                       _tri(rssi, *self.rssi_mfs[rn]))       # min (Mamdani)
            if fire <= 0:
                continue
            mf = np.array([min(fire, _tri(y, *self.weight_mfs[wn])) for y in ys])
            agg = np.maximum(agg, mf)                        # max 결합
        if agg.sum() == 0:
            return 0.5
        return float((ys * agg).sum() / agg.sum())           # 무게중심 역퍼지화


class FuzzyWknnEstimator:
    """P9 Eq.(4)-(5) 퍼지 가중 WKNN. FingerprintDB 재사용 (beacon_ids 정렬 공유).

    type2=True 이면 상/하 MF 두 벌의 추론 평균(구간 축약) 사용 (P9 §2.2.3).
    """

    def __init__(self, db: FingerprintDB, beacon_xy: Dict[str, Tuple[float, float]],
                 k: int = 4, type2: bool = True, spread: float = 3.0,
                 eps: float = 1e-6) -> None:
        self.db, self.k, self.eps = db, int(k), eps
        self.beacon_xy = beacon_xy
        self._fis_lo = _Mamdani(0.0)
        self._fis_hi = _Mamdani(spread) if type2 else None

    def _weight(self, dist_m: float, rssi: float) -> float:
        w = self._fis_lo.infer(dist_m, rssi)
        if self._fis_hi is not None:
            w = 0.5 * (w + self._fis_hi.infer(dist_m, rssi))  # 구간 축약 (Type-2)
        return w

    def estimate(self, rssi_by_beacon: Dict[str, float]) -> Optional[PositionEstimate]:
        if len(self.db) == 0:
            return None
        bids = self.db.beacon_ids
        q = np.array([rssi_by_beacon.get(b, MISSING_RSSI) for b in bids])
        pts = self.db.points
        vecs = self.db.vectors
        D = np.zeros(len(self.db))
        for i in range(len(self.db)):
            acc = 0.0
            for j, b in enumerate(bids):
                if b not in self.beacon_xy:
                    continue
                bx, by = self.beacon_xy[b]
                geo = float(np.hypot(pts[i, 0] - bx, pts[i, 1] - by))
                w_ij = self._weight(min(geo, 10.0), float(q[j]))
                acc += ((vecs[i, j] - q[j]) * w_ij) ** 2      # P9 Eq.(5)
            D[i] = np.sqrt(acc)
        k = min(self.k, len(self.db))
        idx = np.argsort(D)[:k]
        w = 1.0 / (D[idx] + self.eps)
        p = (pts[idx] * w[:, None]).sum(axis=0) / w.sum()     # P9 Eq.(4)
        return PositionEstimate(float(p[0]), float(p[1]), "fuzzy-wknn", k,
                                meta={"signal_dist": float(D[idx].mean())})
