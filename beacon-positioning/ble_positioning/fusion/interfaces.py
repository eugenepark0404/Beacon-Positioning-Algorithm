"""트랙2(센서퓨전) 연동 규격 — 억지 구현 X, 인터페이스 정의 O.

# ref: P2 §3 (BLE+IMU PF 융합 구조), P5 (PF + 도면 사후보정 → 훅 포함), 유도서 §5
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Optional, Tuple


@dataclass
class PdrStep:
    """트랙2 PDR(보행자 추측항법) 입력 규격. # ref: P2 Eq.(18) V_I = L_s/(t_i - t_{i-1})"""
    timestamp: float          # [s]
    step_length_m: float      # 보폭 L_s [m]
    heading_rad: float        # 진행 방위각 (Madgwick 등 자세필터 처리 후, P2 §3.3)
    heading_delta_rad: float = 0.0  # 직전 대비 방향 변화 (P2 이동모델의 delta-alpha)


@dataclass
class BlePositionInput:
    """트랙1 BLE 단독 측위 결과 → 융합 입력."""
    timestamp: float
    x: float
    y: float
    sigma_m: float            # 추정 불확실성 (PF 우도 sigma_ble)


class FusionEngine(ABC):
    """융합 엔진 공통 규약. 트랙2는 이 규약을 구현/교체한다."""

    @abstractmethod
    def update_ble(self, obs: BlePositionInput) -> None: ...

    @abstractmethod
    def update_pdr(self, step: PdrStep) -> None: ...

    @abstractmethod
    def estimate(self) -> Optional[Tuple[float, float]]: ...

    # P5(FP-BP) 도면 사후보정 훅: 위치 -> 보정 위치 (예: 벽 통과 금지, 통로 스냅)
    map_constraint: Optional[Callable[[float, float], Tuple[float, float]]] = None
