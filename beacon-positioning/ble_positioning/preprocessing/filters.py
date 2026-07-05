"""RSSI 안정화: 이동창(중앙값/평균/최빈값), 1D 칼만, MAD 이상치 제거.

# ref: P3 §III-B(측정 창), §V-A(median/윈도우10 최적) / P4 §2.3.4(KF) / 유도서 §4
"""
from __future__ import annotations

from collections import defaultdict, deque
from statistics import mode, StatisticsError
from typing import Dict, List, Optional

import numpy as np

from ..ingest.loaders import RssiSample


class SlidingWindowFilter:
    """비콘별(채널별) 독립 슬라이딩 윈도우. # ref: P3 Fig.1"""

    def __init__(self, window_size: int = 10, method: str = "median") -> None:
        if method not in ("median", "mean", "mode"):
            raise ValueError(f"unknown method: {method}")
        self.window_size = int(window_size)
        self.method = method
        self._buf: Dict[str, deque] = defaultdict(lambda: deque(maxlen=self.window_size))

    @staticmethod
    def _key(beacon_id: str, channel: Optional[int]) -> str:
        return f"{beacon_id}#{channel if channel is not None else 'agg'}"

    def update(self, beacon_id: str, rssi: float, channel: Optional[int] = None) -> float:
        buf = self._buf[self._key(beacon_id, channel)]
        buf.append(float(rssi))
        vals = list(buf)
        if self.method == "mean":
            return float(np.mean(vals))
        if self.method == "mode":
            try:
                return float(mode(vals))
            except StatisticsError:
                return float(np.median(vals))  # P3: mode 부재 시 median fallback
        return float(np.median(vals))

    def reset(self) -> None:
        self._buf.clear()


class RssiKalman1D:
    """RSSI 스칼라 칼만 필터 (정적 상태 모델). # ref: P4 §2.3.4 / 유도서 §4.2

    x_hat- = x_hat ; P- = P + Q
    K = P-/(P-+R) ; x_hat += K(z - x_hat-) ; P = (1-K)P-
    """

    def __init__(self, q: float = 0.05, r: float = 4.0) -> None:
        self.q, self.r = float(q), float(r)
        self._x: Dict[str, float] = {}
        self._p: Dict[str, float] = {}

    def update(self, key: str, z: float) -> float:
        if key not in self._x:
            self._x[key], self._p[key] = float(z), self.r
            return float(z)
        p_pred = self._p[key] + self.q          # 예측
        k = p_pred / (p_pred + self.r)          # 칼만 이득
        self._x[key] += k * (float(z) - self._x[key])
        self._p[key] = (1.0 - k) * p_pred
        return self._x[key]

    def reset(self) -> None:
        self._x.clear(); self._p.clear()


def remove_outliers_mad(values: List[float], k: float = 3.0) -> List[float]:
    """중앙값 절대편차(MAD) 기반 이상치 제거. # ref: 유도서 §4.3 (P4 중앙값 권고 부합)"""
    if len(values) < 3:
        return list(values)
    arr = np.asarray(values, dtype=float)
    med = np.median(arr)
    mad = np.median(np.abs(arr - med))
    if mad == 0:
        return list(values)
    keep = np.abs(arr - med) <= k * 1.4826 * mad
    return arr[keep].tolist()


def aggregate_by_beacon(samples: List[RssiSample], mad_k: float = 3.0) -> Dict[str, float]:
    """스캔 창 내 샘플을 비콘별 대표 RSSI(중앙값)로 집계. 채널 구분은 correction 단계에서 사용."""
    grouped: Dict[str, List[float]] = defaultdict(list)
    for s in samples:
        grouped[s.beacon_id].append(s.rssi)
    out: Dict[str, float] = {}
    for bid, vals in grouped.items():
        vals = remove_outliers_mad(vals, k=mad_k)
        if vals:
            out[bid] = float(np.median(vals))   # ref: P3 §V-A median 최적
    return out
