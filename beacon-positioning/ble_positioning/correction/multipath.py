"""다중경로/NLoS 판별 + 신호 요동 완화.

# ref: P1 §1(채널별 페이딩 vs 전채널 차폐), P2 §2.2(오차원 분류), 유도서 §3.5
"""
from __future__ import annotations

from typing import Dict, Optional

import numpy as np


def classify_channel_event(rssi_by_channel: Dict[int, float],
                           baseline_by_channel: Dict[int, float],
                           drop_db: float = 4.0,
                           spread_db: float = 6.0) -> str:
    """채널 패턴으로 이벤트 분류. 반환: 'shadow' | 'multipath' | 'normal'

    - 전 채널 동시 하락(>= drop_db)          → shadow    # ref: P1 §2.2
    - 채널 간 편차 급증(>= spread_db) 인데
      전 채널 하락은 아님                     → multipath # ref: P1 §1
    """
    if not rssi_by_channel or not baseline_by_channel:
        return "normal"
    common = [ch for ch in rssi_by_channel if ch in baseline_by_channel]
    if len(common) < 2:
        return "normal"
    drops = np.array([baseline_by_channel[ch] - rssi_by_channel[ch] for ch in common])
    vals = np.array([rssi_by_channel[ch] for ch in common])
    if np.all(drops >= drop_db):
        return "shadow"
    if (vals.max() - vals.min()) >= spread_db and not np.all(drops >= drop_db):
        return "multipath"
    return "normal"


class FluctuationDamper:
    """RSSI 급변 억제(레이트 리미터). 채널 정보가 없는 집계 스트림용 완화 장치.

    물리적으로 보행 중 거리 변화가 만드는 RSSI 변화율은 제한적이라는 관찰(P3 §V-A.2,
    윈도우-보행속도 트레이드오프)에 기반한 보수적 휴리스틱. 논문 수식 아님 — 명시적 휴리스틱.
    """

    def __init__(self, max_delta_db_per_s: float = 10.0) -> None:
        self.max_rate = float(max_delta_db_per_s)
        self._last: Dict[str, tuple] = {}

    def update(self, key: str, t: float, rssi: float) -> float:
        if key in self._last:
            t0, v0 = self._last[key]
            dt = max(t - t0, 1e-3)
            limit = self.max_rate * dt
            rssi = float(np.clip(rssi, v0 - limit, v0 + limit))
        self._last[key] = (t, rssi)
        return rssi
