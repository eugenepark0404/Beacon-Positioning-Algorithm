"""인체 차폐(body-shadowing) 감지·보정 — 이 과제의 심장.

# ref: P1 (MDPI Sensors 2020) 전반, 유도서 §3
원리: 다중경로는 채널별로 다르게, 인체 차폐는 3개 광고 채널(37/38/39)을 동시에 감쇠시킨다.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from ..config.settings import ShadowParams


@dataclass
class ShadowDecision:
    blocked: bool
    corrected_rssi: Dict[int, float]   # 채널 -> 보정 RSSI
    confidence: float = 0.0
    detector: str = "threshold"


class ThresholdShadowDetector:
    """차폐 감지 상태기계 + 고정 감쇠 보상.

    # ref: P1 §2.2 Fig.1b (유도서 §3.2): 인체 차폐는 3개 광고 채널을 '동시에·급격히'
    # 감쇠시키고, 인체가 벗어나면 원래 값으로 복귀한다. 이동 수신기에서는 거리 변화가
    # 만드는 완만한 RSSI 변화(~수 dB/s)와 차폐의 급락(수 dB/윈도우)을 구분해야 하므로,
    # 롤링 평균(P1 [9]) 대신 EMA 기준선 + 급락/회복 상태기계로 구현한다.
    # 감지 임계 shadow_drop_db, 보상량 shadow_atten_db는 config (트랙3 실측 교체).
    """

    def __init__(self, params: ShadowParams) -> None:
        self.p = params
        self._ema: Dict[Tuple[str, int], float] = {}      # (beacon, ch) -> 무차폐 기준선
        self._shadowed: Dict[str, int] = {}               # beacon -> 차폐 지속 윈도우 수
        self._alpha = 0.6                                  # EMA 계수 (1s 창 기준; 보행 드리프트 추종)
        self._max_hold = max(3, params.window_size // 2)   # 차폐 최대 유지 창 수 (인체 통과는 수 초 # ref: P1 §2.2)

    def update(self, beacon_id: str, rssi_by_channel: Dict[int, float]) -> ShadowDecision:
        chans = list(rssi_by_channel)
        # 기준선 미형성 채널은 현재값으로 초기화
        for ch in chans:
            self._ema.setdefault((beacon_id, ch), rssi_by_channel[ch])
        drops = [self._ema[(beacon_id, ch)] - rssi_by_channel[ch] for ch in chans]
        in_shadow = beacon_id in self._shadowed

        if not in_shadow:
            # 진입: 모든 채널 동시 급락 # ref: P1 §2.2 (전 채널 동시 감쇠)
            if len(chans) >= 2 and all(d >= self.p.shadow_drop_db for d in drops):
                self._shadowed[beacon_id] = 1
                in_shadow = True
        else:
            # 회복: 모든 채널이 기준선 부근 복귀 # ref: P1 Fig.1b
            if all(d <= self.p.shadow_drop_db * 0.5 for d in drops):
                del self._shadowed[beacon_id]
                in_shadow = False
            else:
                self._shadowed[beacon_id] += 1
                if self._shadowed[beacon_id] > self._max_hold:
                    # 지속 감쇠 = 환경 변화로 재해석 → 기준선 재적응 (오탐 고착 방지)
                    del self._shadowed[beacon_id]
                    for ch in chans:
                        self._ema[(beacon_id, ch)] = rssi_by_channel[ch]
                    in_shadow = False

        corrected = dict(rssi_by_channel)
        if in_shadow:
            # 감쇠 보상; 차폐 중엔 기준선 갱신 정지 (오염 방지)
            corrected = {ch: v + self.p.shadow_atten_db for ch, v in corrected.items()}
        else:
            for ch in chans:
                k = (beacon_id, ch)
                self._ema[k] = (1 - self._alpha) * self._ema[k] + self._alpha * rssi_by_channel[ch]
        conf = float(np.mean([d >= self.p.shadow_drop_db for d in drops])) if drops else 0.0
        return ShadowDecision(in_shadow, corrected, conf, "threshold")


def build_windows(rssi_series: Dict[int, Sequence[float]], n: int = 10,
                  ) -> Optional[np.ndarray]:
    """채널별 최근 N샘플 → ANN 입력 벡터(3*N차원). # ref: P1 §2.3 (N=10)"""
    chans = sorted(rssi_series.keys())
    rows = []
    for ch in chans:
        seq = list(rssi_series[ch])
        if len(seq) < n:
            return None
        rows.append(seq[-n:])
    return np.concatenate(rows)


class MlShadowCorrector:
    """ANN 기반 차폐 감지+RSSI 보정 (P1 §2.3의 MLP 방식).

    입력: 채널별 N=10 슬라이딩 윈도우 (3ch x 10 = 30차원)   # ref: P1 §2.3
    출력: 채널별 보정 RSSI + 차폐 플래그                     # ref: P1 §2.3
    구조: 은닉 2층 x 20뉴런 MLP                              # ref: P1 §2.3.1
    학습 타깃: 동일 위치의 '차폐 없는' 실측 RSSI (모델값 아님) # ref: P1 §2.3
    성능 기대치: 감지율 ~89%, LoS 정분류 ~94% (P1 §3)
    """

    def __init__(self, params: ShadowParams, random_state: int = 0) -> None:
        from sklearn.neural_network import MLPRegressor, MLPClassifier
        from sklearn.preprocessing import StandardScaler
        self.p = params
        self.n = params.window_size
        # 입력 표준화: MLP 학습 안정화 (P1은 dB 원값 사용을 명시하지 않음 — 표준 전처리)
        self.scaler = StandardScaler()
        self.regressor = MLPRegressor(hidden_layer_sizes=tuple(params.mlp_hidden),
                                      max_iter=3000, random_state=random_state)
        self.classifier = MLPClassifier(hidden_layer_sizes=tuple(params.mlp_hidden),
                                        max_iter=3000, random_state=random_state)
        self.trained = False

    def fit(self, X_windows: np.ndarray, y_clean_rssi: np.ndarray,
            y_blocked: np.ndarray) -> "MlShadowCorrector":
        """X: (m, 3N) 윈도우, y_clean_rssi: (m, 3) 무차폐 타깃, y_blocked: (m,) 0/1.

        70/30 분할 검증은 호출측(트랙3 실측/시뮬 학습 스크립트) 책임. # ref: P1 §3
        """
        Xs = self.scaler.fit_transform(X_windows)
        self.regressor.fit(Xs, y_clean_rssi)
        self.classifier.fit(Xs, y_blocked.astype(int))
        self.trained = True
        return self

    def predict(self, window: np.ndarray) -> Tuple[np.ndarray, bool, float]:
        """반환: (보정 RSSI[3], 차폐 여부, 차폐 확률)"""
        if not self.trained:
            raise RuntimeError("MlShadowCorrector: fit() 먼저 호출 (트랙3 실측 or 시뮬 데이터)")
        w = self.scaler.transform(np.asarray(window, dtype=float).reshape(1, -1))
        rssi = self.regressor.predict(w)[0]
        proba = float(self.classifier.predict_proba(w)[0, 1])
        return np.atleast_1d(rssi), proba >= 0.5, proba
