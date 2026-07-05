"""위치 추정기: 선형/비선형 최소제곱 다변측량, WCL, 확률 그리드, KNN 핑거프린팅.

# ref: 유도서 §2 (P4 Eq.(3)-(5), P1 §2, P3 Eq.(4)-(9), P8)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from scipy.optimize import least_squares

XY = Tuple[float, float]


@dataclass
class PositionEstimate:
    x: float
    y: float
    method: str
    n_beacons: int
    residual: float = 0.0          # 최소제곱 잔차 (신뢰도 지표)
    meta: dict = field(default_factory=dict)


def _arrays(beacons: Dict[str, XY], dists: Dict[str, float]):
    ids = [b for b in dists if b in beacons]
    S = np.array([beacons[b] for b in ids], dtype=float)
    r = np.array([dists[b] for b in ids], dtype=float)
    return ids, S, r


def trilaterate_linear(beacons: Dict[str, XY], dists: Dict[str, float],
                       ) -> Optional[PositionEstimate]:
    """선형화 최소제곱 다변측량. # ref: P4 Eq.(3)-(5), 유도서 §2.1

    i번째 원 방정식에서 1번째를 빼 X^2,Y^2 소거 → M p = b → lstsq.
    """
    ids, S, r = _arrays(beacons, dists)
    if len(ids) < 3:
        return None
    x1, y1, r1 = S[0, 0], S[0, 1], r[0]
    M = np.column_stack([-2 * x1 + 2 * S[1:, 0], -2 * y1 + 2 * S[1:, 1]])
    b = ((r1 ** 2 - x1 ** 2 - y1 ** 2)
         - (r[1:] ** 2 - S[1:, 0] ** 2 - S[1:, 1] ** 2))
    sol, res, rank, _ = np.linalg.lstsq(M, b, rcond=None)
    if rank < 2:
        return None  # 비콘이 일직선상 (특이) → 상위에서 WCL fallback
    resid = float(res[0]) if res.size else 0.0
    return PositionEstimate(float(sol[0]), float(sol[1]), "linear", len(ids), resid)


def trilaterate_nls(beacons: Dict[str, XY], dists: Dict[str, float],
                    weight_g: float = 0.0, x0: Optional[XY] = None,
                    ) -> Optional[PositionEstimate]:
    """비선형 파라메트릭 최소제곱. # ref: P1 §2, 유도서 §2.2

    p* = argmin Σ w_i (||S_i - p|| - r_i)^2 ,  w_i = 1/r_i^g (근거리 신뢰, P4 §3.1)
    초기값: 선형해 → 실패 시 가중중심.
    """
    ids, S, r = _arrays(beacons, dists)
    if len(ids) < 3:
        return None
    if x0 is None:
        lin = trilaterate_linear(beacons, dists)
        x0 = (lin.x, lin.y) if lin else tuple(np.average(S, axis=0, weights=1.0 / np.maximum(r, 0.1)))
    w = 1.0 / np.maximum(r, 0.1) ** weight_g if weight_g > 0 else np.ones_like(r)
    sw = np.sqrt(w)

    def residuals(p):
        return sw * (np.hypot(S[:, 0] - p[0], S[:, 1] - p[1]) - r)

    sol = least_squares(residuals, x0=np.asarray(x0, dtype=float), method="lm")
    return PositionEstimate(float(sol.x[0]), float(sol.x[1]), "nls", len(ids),
                            float(np.sum(sol.fun ** 2)))


def weighted_centroid(beacons: Dict[str, XY], dists: Dict[str, float],
                      g: float = 2.5) -> Optional[PositionEstimate]:
    """가중 중심(WCL). # ref: P3 Eq.(6)-(7), 유도서 §2.3. g 최적 2.0~3.5 (P3 §V-B)."""
    ids, S, r = _arrays(beacons, dists)
    if len(ids) == 0:
        return None
    w = 1.0 / np.maximum(r, 0.1) ** g          # Eq.(7)
    p = (S * w[:, None]).sum(axis=0) / w.sum() # Eq.(6)
    return PositionEstimate(float(p[0]), float(p[1]), "wcl", len(ids))


def grid_probability(beacons: Dict[str, XY], dists: Dict[str, float],
                     bounds: Tuple[float, float, float, float],
                     step: float = 0.25, c: float = 1.0) -> Optional[PositionEstimate]:
    """확률 기반 그리드 측위. # ref: P3 Eq.(8)-(9), 유도서 §2.4 (P5 GML 동계열)

    p(d,d_i) = 1/((d-d_i)^2 + c) ; 격자점별 곱 → argmax.
    """
    ids, S, r = _arrays(beacons, dists)
    if len(ids) < 2:
        return None
    xmin, ymin, xmax, ymax = bounds
    xs = np.arange(xmin, xmax + step, step)
    ys = np.arange(ymin, ymax + step, step)
    gx, gy = np.meshgrid(xs, ys)
    logp = np.zeros_like(gx)
    for (bx, by), ri in zip(S, r):
        d = np.hypot(gx - bx, gy - by)
        logp += np.log(1.0 / ((d - ri) ** 2 + c))       # Eq.(8), log-곱 안정화
    j = np.unravel_index(np.argmax(logp), logp.shape)
    return PositionEstimate(float(gx[j]), float(gy[j]), "grid", len(ids),
                            meta={"log_prob": float(logp[j])})


MISSING_RSSI = -100.0  # 결측 비콘 대치값 (매우 약한 신호)


class FingerprintDB:
    """핑거프린트 지도: 참조점 좌표 + 비콘별 RSSI 벡터. # ref: P8, 유도서 §2.5"""

    def __init__(self, beacon_ids: Sequence[str]) -> None:
        self.beacon_ids = list(beacon_ids)
        self._points: List[XY] = []
        self._vectors: List[np.ndarray] = []

    def add(self, xy: XY, rssi_by_beacon: Dict[str, float]) -> None:
        vec = np.array([rssi_by_beacon.get(b, MISSING_RSSI) for b in self.beacon_ids])
        self._points.append((float(xy[0]), float(xy[1])))
        self._vectors.append(vec)

    @property
    def points(self) -> np.ndarray:
        return np.asarray(self._points)

    @property
    def vectors(self) -> np.ndarray:
        return np.asarray(self._vectors)

    def __len__(self) -> int:
        return len(self._points)


class KnnEstimator:
    """KNN/WKNN 핑거프린팅. # ref: P8 (KNN 계열 54건 최다 → 베이스라인), 유도서 §2.5"""

    def __init__(self, db: FingerprintDB, k: int = 4, weighted: bool = True,
                 eps: float = 1e-6) -> None:
        self.db, self.k, self.weighted, self.eps = db, int(k), weighted, eps

    def estimate(self, rssi_by_beacon: Dict[str, float]) -> Optional[PositionEstimate]:
        if len(self.db) == 0:
            return None
        q = np.array([rssi_by_beacon.get(b, MISSING_RSSI) for b in self.db.beacon_ids])
        D = np.linalg.norm(self.db.vectors - q, axis=1)     # 신호공간 유클리드 거리
        k = min(self.k, len(self.db))
        idx = np.argsort(D)[:k]
        pts = self.db.points[idx]
        if self.weighted:
            w = 1.0 / (D[idx] + self.eps)                   # WKNN 가중
            p = (pts * w[:, None]).sum(axis=0) / w.sum()
        else:
            p = pts.mean(axis=0)
        return PositionEstimate(float(p[0]), float(p[1]),
                                "wknn" if self.weighted else "knn", k,
                                meta={"signal_dist": float(D[idx].mean())})


# 확장 구현: GmlEstimator(P5, gml.py), FuzzyWknnEstimator(P9, fuzzy.py).
# CNN(PSO 최적화) 추정기는 동일한 .estimate() 규약을 따라 추가한다 (훅).
