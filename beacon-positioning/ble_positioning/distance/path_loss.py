"""RSSI ↔ 거리 변환: 로그-거리 경로손실 모델.

# ref: P1 Eq.(1): RSSI(d) = A - 10 n log10(d/d0)
# 역변환(유도서 §1.3): d = d0 * 10^((A - RSSI)/(10 n))
# 부호 주의: P3 Eq.(2)-(3) 인쇄본과 달리 물리적으로 올바른 형태 채택 (유도서 §1.3 검산 참조)
"""
from __future__ import annotations

from typing import Sequence, Tuple

import numpy as np

from ..config.settings import PathLossParams


class LogDistanceModel:
    def __init__(self, params: PathLossParams) -> None:
        self.p = params

    def rssi_to_distance(self, rssi: float) -> float:
        """d = d0 * 10^((A - RSSI)/(10 n))  # ref: P1 Eq.(1) 역변환"""
        d = self.p.d0_m * 10.0 ** ((self.p.a_dbm - float(rssi)) / (10.0 * self.p.n))
        return float(np.clip(d, 0.01, self.p.max_range_m))

    def distance_to_rssi(self, d: float) -> float:
        """RSSI = A - 10 n log10(d/d0)  # ref: P1 Eq.(1)"""
        d = max(float(d), 1e-6)
        return self.p.a_dbm - 10.0 * self.p.n * np.log10(d / self.p.d0_m)


def fit_log_distance(distances_m: Sequence[float], rssis_dbm: Sequence[float],
                     d0_m: float = 1.0) -> Tuple[float, float]:
    """실측 (거리, RSSI) 쌍에서 (n, A) 회귀 추정. 트랙3 캘리브레이션용.

    RSSI = A - n * [10 log10(d/d0)]  →  y = A - n*x 선형 최소제곱.
    # ref: P1 §2 (채널별 empirical path loss exponent), 유도서 §1.4
    """
    d = np.asarray(distances_m, dtype=float)
    y = np.asarray(rssis_dbm, dtype=float)
    if d.size < 2:
        raise ValueError("need >= 2 calibration points")
    x = 10.0 * np.log10(d / d0_m)
    slope, intercept = np.polyfit(x, y, 1)   # y = slope*x + intercept
    n = -float(slope)
    a = float(intercept)
    return n, a
