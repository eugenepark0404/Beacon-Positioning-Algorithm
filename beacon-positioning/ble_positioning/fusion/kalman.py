"""등속(CV) 칼만 필터 골격 — 트랙2 대안 융합기 규격.

상태 [x, y, vx, vy], 관측 [x, y]. 표준 KF 수식 (유도서 §4.2의 벡터 확장).
가우시안 한정(비가우시안 잡음엔 PF 권장 # ref: P2 §3 서두) — 비교 실험용.
"""
from __future__ import annotations

from typing import Optional, Tuple

import numpy as np

from .interfaces import BlePositionInput, FusionEngine, PdrStep


class ConstantVelocityKalman(FusionEngine):
    def __init__(self, q: float = 0.5, r: float = 2.0) -> None:
        self.q, self.r = float(q), float(r)
        self.x: Optional[np.ndarray] = None   # [x, y, vx, vy]
        self.P = np.eye(4) * 10.0
        self._t: Optional[float] = None
        self.map_constraint = None

    def _predict(self, dt: float) -> None:
        F = np.eye(4)
        F[0, 2] = F[1, 3] = dt
        G = np.array([[0.5 * dt ** 2, 0], [0, 0.5 * dt ** 2], [dt, 0], [0, dt]])
        Q = G @ G.T * self.q ** 2
        self.x = F @ self.x
        self.P = F @ self.P @ F.T + Q

    def update_ble(self, obs: BlePositionInput) -> None:
        z = np.array([obs.x, obs.y])
        if self.x is None:
            self.x = np.array([obs.x, obs.y, 0.0, 0.0])
            self._t = obs.timestamp
            return
        dt = max(obs.timestamp - (self._t or obs.timestamp), 1e-3)
        self._predict(dt)
        self._t = obs.timestamp
        H = np.zeros((2, 4)); H[0, 0] = H[1, 1] = 1.0
        R = np.eye(2) * max(obs.sigma_m, self.r) ** 2
        S = H @ self.P @ H.T + R
        K = self.P @ H.T @ np.linalg.inv(S)
        self.x = self.x + K @ (z - H @ self.x)
        self.P = (np.eye(4) - K @ H) @ self.P

    def update_pdr(self, step: PdrStep) -> None:
        # 규격만 정의: PDR 속도 관측으로의 확장은 트랙2 구현 지점.
        pass

    def estimate(self) -> Optional[Tuple[float, float]]:
        if self.x is None:
            return None
        x, y = float(self.x[0]), float(self.x[1])
        if self.map_constraint is not None:
            x, y = self.map_constraint(x, y)
        return (x, y)
