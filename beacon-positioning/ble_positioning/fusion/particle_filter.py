"""BLE(+IMU) 파티클 필터 — P2의 이동모델·우도·재샘플링 골격.

# ref: P2 §3.1 Eq.(7)-(8), §3.2 Eq.(9)-(17), §3.3 Eq.(18)-(21), §3.5 Eq.(28), 유도서 §5
MCPD 우도(Eq.22-27)는 채널사운딩 HW 전용 → '베이스라인 있는 가우시안' 형태만 차용(유도서 §5.4).
"""
from __future__ import annotations

from typing import Optional, Tuple

import numpy as np

from ..config.settings import ParticleFilterParams
from .interfaces import BlePositionInput, FusionEngine, PdrStep


class ParticleFilter2D(FusionEngine):
    """상태 = (X, Y, Vx, Vy) x N 파티클. # ref: P2 §3.2"""

    def __init__(self, params: ParticleFilterParams,
                 bounds: Tuple[float, float, float, float],
                 rng: Optional[np.random.Generator] = None) -> None:
        self.p = params
        self.bounds = bounds
        self.rng = rng or np.random.default_rng(0)
        n = params.n_particles
        xmin, ymin, xmax, ymax = bounds
        # 초기: 균일 분포, 균일 가중 # ref: P2 §3.1
        self.X = self.rng.uniform(xmin, xmax, n)
        self.Y = self.rng.uniform(ymin, ymax, n)
        self.Vx = np.zeros(n)
        self.Vy = np.zeros(n)
        self.w = np.full(n, 1.0 / n)
        self._t: Optional[float] = None
        self.map_constraint = None

    # ---------- 예측 (이동 모델) ----------
    def _predict(self, dt: float, heading_delta: float = 0.0) -> None:
        """# ref: P2 Eq.(9)-(14), 파라미터 Eq.(15)-(17)"""
        n = self.X.size
        r_xy = self.rng.normal(0.0, self.p.sigma_xy, n)
        self.X += self.Vx * dt + r_xy * dt                       # Eq.(9)
        r_xy = self.rng.normal(0.0, self.p.sigma_xy, n)
        self.Y += self.Vy * dt + r_xy * dt                       # Eq.(10)
        self.Vx += self.rng.normal(0.0, self.p.sigma_v, n) * dt  # Eq.(11)
        self.Vy += self.rng.normal(0.0, self.p.sigma_v, n) * dt  # Eq.(12)
        theta = heading_delta + self.rng.normal(0.0, self.p.sigma_alpha, n)
        vx = self.Vx * np.cos(theta) - self.Vy * np.sin(theta)   # Eq.(13)
        vy = self.Vy * np.cos(theta) + self.Vx * np.sin(theta)   # Eq.(14)
        self.Vx, self.Vy = vx, vy

    def _advance(self, t: float, heading_delta: float = 0.0) -> None:
        if self._t is None:
            self._t = t
            return
        dt = t - self._t
        if dt > 0:
            self._predict(dt, heading_delta)
            self._t = t

    # ---------- 갱신 ----------
    def update_ble(self, obs: BlePositionInput) -> None:
        """BLE 위치 우도: L = b_w + (1-b_w) N(dist | 0, sigma^2). # ref: P2 Eq.(27) 형태 차용"""
        self._advance(obs.timestamp)
        d = np.hypot(self.X - obs.x, self.Y - obs.y)
        sigma = max(obs.sigma_m, 1e-3)
        like = self.p.b_w + (1.0 - self.p.b_w) * np.exp(-0.5 * (d / sigma) ** 2)
        self.w *= like                                            # Eq.(8)
        self._normalize_resample()

    def update_pdr(self, step: PdrStep) -> None:
        """IMU 보속 우도. # ref: P2 Eq.(18)-(21)"""
        dt_prev = self._t
        self._advance(step.timestamp, step.heading_delta_rad)
        if dt_prev is None:
            return
        dt = max(step.timestamp - dt_prev, 1e-3)
        v_i = step.step_length_m / dt                             # Eq.(18)
        v2 = self.Vx ** 2 + self.Vy ** 2
        sigma = self.p.sigma_v_like
        like = self.p.b_v + (1.0 - self.p.b_v) * np.exp(
            -0.5 * ((v2 - v_i ** 2) / max(sigma, 1e-6)) ** 2)     # Eq.(19)
        self.w *= like
        self._normalize_resample()

    # ---------- 재샘플 ----------
    def _normalize_resample(self) -> None:
        s = self.w.sum()
        if s <= 0 or not np.isfinite(s):
            self.w[:] = 1.0 / self.w.size
            return
        self.w /= s
        # 유효 파티클 수 기준 systematic resampling # ref: P2 §3.1 [42]
        neff = 1.0 / np.sum(self.w ** 2)
        if neff < self.w.size / 2:
            self._systematic_resample()

    def _systematic_resample(self) -> None:
        n = self.w.size
        positions = (self.rng.random() + np.arange(n)) / n
        cumsum = np.cumsum(self.w)
        cumsum[-1] = 1.0
        idx = np.searchsorted(cumsum, positions)
        for arr in ("X", "Y", "Vx", "Vy"):
            setattr(self, arr, getattr(self, arr)[idx].copy())
        self.w[:] = 1.0 / n

    # ---------- 출력 ----------
    def estimate(self) -> Optional[Tuple[float, float]]:
        """가중 평균. # ref: P2 Eq.(28)"""
        x = float(np.sum(self.w * self.X))
        y = float(np.sum(self.w * self.Y))
        if self.map_constraint is not None:      # P5 도면 사후보정 훅
            x, y = self.map_constraint(x, y)
        return (x, y)
