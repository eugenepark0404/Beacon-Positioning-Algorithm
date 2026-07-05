"""GML (Grid-based Maximum Likelihood) BLE 측위 — P5 (FP-BP, arXiv:2504.09905) §III.

핵심: RSSI 노이즈 X~N(0,σ²)가 로그-거리 모델을 지나면 추정거리 d̂는
로그정규분포 LN₁₀(log d, η²), η = σ̂/(10n) 를 따른다 (P5 Eq.(10)-(13)).
따라서 우도를 '거리'가 아니라 'log 거리' 오차로 세워야 노이즈 통계와 일치한다:

  y* = argmin_{y∈G'} Σᵢ (1/2ηᵢ²)(log₁₀ d̂ᵢ − log₁₀‖y−bᵢ‖)²   (P5 Eq.(19))

후보 격자 G' = (전체 격자 ∩ 선택 비콘 볼록껍질 내부) ∧ 이전 위치와의 맨해튼
거리 < d₀ (P5 Eq.(20); 희소 배치면 껍질 제약 제외, Eq.(21)).
시간 평활: 최근 n개 BLE 결과 평균 (P5 Eq.(22)).
P5 실측: 보행 중 평균 오차 2.01 m — 삼변측량(9.39 m)·ML(2.63 m) 대비 우수.
"""
from __future__ import annotations

from collections import deque
from typing import Dict, Optional, Tuple

import numpy as np

from .estimators import PositionEstimate

XY = Tuple[float, float]


class GmlEstimator:
    """상태 보유(시간 평활·이전 위치) — 파이프라인당 1개 인스턴스 사용."""

    def __init__(self, beacons: Dict[str, XY],
                 bounds: Tuple[float, float, float, float],
                 grid_step: float = 0.3,      # P5 Table: virtual grid interval 0.3 m
                 top_n: int = 5,              # RSSI 상위 N개 선택 (P5 §III, N>=3)
                 eta: float = 0.1,            # η = σ̂/(10n) (P5 Eq.(12); σ̂=2dB,n=2 → 0.1)
                 d0_manhattan: float = 6.0,   # 후보 반경 (P5 Eq.(20) d₀) PLACEHOLDER
                 avg_n: int = 3,              # 시간 평활 창 (P5 Eq.(22) n)
                 restrict_hull: bool = True) -> None:
        self.beacons = beacons
        self.top_n = top_n
        self.eta = eta
        self.d0 = d0_manhattan
        self.restrict_hull = restrict_hull
        self._hist: deque = deque(maxlen=max(1, avg_n))
        self._prev: Optional[np.ndarray] = None
        xmin, ymin, xmax, ymax = bounds
        xs = np.arange(xmin, xmax + grid_step, grid_step)
        ys = np.arange(ymin, ymax + grid_step, grid_step)
        gx, gy = np.meshgrid(xs, ys)
        self._grid = np.column_stack([gx.ravel(), gy.ravel()])   # 전체 격자 G (P5 §IV-A4)

    def _candidates(self, sel_xy: np.ndarray) -> np.ndarray:
        """G' 구성. # ref: P5 Eq.(20)-(21)"""
        g = self._grid
        if self.restrict_hull and len(sel_xy) >= 3:
            try:
                from scipy.spatial import Delaunay
                hull = Delaunay(sel_xy)
                mask = hull.find_simplex(g) >= 0     # 볼록껍질 내부 (P5: int CH(B_N))
                if mask.any():
                    g = g[mask]
            except Exception:
                pass  # 퇴화(일직선 비콘 등) → 껍질 제약 생략 (Eq.(21) 모드)
        if self._prev is not None:
            man = np.abs(g - self._prev).sum(axis=1)  # 맨해튼 거리 (P5 Eq.(20))
            near = man < self.d0
            if near.any():
                g = g[near]
        return g

    def estimate(self, dists: Dict[str, float],
                 rssi_by_beacon: Optional[Dict[str, float]] = None,
                 ) -> Optional[PositionEstimate]:
        ids = [b for b in dists if b in self.beacons]
        if len(ids) < 3:
            return None
        # RSSI 상위 N개 선택 (P5 Eq.(9); rssi 없으면 근거리 N개로 대체)
        if rssi_by_beacon:
            ids.sort(key=lambda b: rssi_by_beacon.get(b, -999), reverse=True)
        else:
            ids.sort(key=lambda b: dists[b])
        ids = ids[: self.top_n]
        S = np.array([self.beacons[b] for b in ids], dtype=float)
        d_hat = np.array([max(dists[b], 0.05) for b in ids])

        cand = self._candidates(S)
        if cand.size == 0:
            return None
        # log-거리 잔차 제곱합 (P5 Eq.(19)); ηᵢ 동일 가정 (P5 §III 말미)
        diff = cand[:, None, :] - S[None, :, :]
        d_geo = np.maximum(np.linalg.norm(diff, axis=2), 0.05)
        cost = ((np.log10(d_hat)[None, :] - np.log10(d_geo)) ** 2).sum(axis=1) \
            / (2.0 * self.eta ** 2)
        y_star = cand[int(np.argmin(cost))]

        # 시간 평활 (P5 Eq.(22))
        self._hist.append(y_star)
        avg = np.mean(np.asarray(self._hist), axis=0)
        self._prev = avg
        return PositionEstimate(float(avg[0]), float(avg[1]), "gml", len(ids),
                                residual=float(cost.min()),
                                meta={"raw_x": float(y_star[0]), "raw_y": float(y_star[1])})

    def reset(self) -> None:
        self._hist.clear()
        self._prev = None
