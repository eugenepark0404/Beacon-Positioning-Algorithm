"""차폐 감지(3채널 규칙)·다중경로 판별·ML 보정기 검증. # ref: P1"""
import numpy as np

from ble_positioning.config.settings import ShadowParams
from ble_positioning.correction.shadowing import (
    ThresholdShadowDetector, MlShadowCorrector, build_windows,
)
from ble_positioning.correction.multipath import classify_channel_event


def test_threshold_detects_all_channel_drop():
    det = ThresholdShadowDetector(ShadowParams(shadow_atten_db=7.0, shadow_drop_db=4.5))
    rng = np.random.default_rng(0)
    for _ in range(10):  # 무차폐 기준선 형성
        det.update("b1", {37: -60 + rng.normal(0, 1), 38: -62 + rng.normal(0, 1),
                          39: -61 + rng.normal(0, 1)})
    dec = det.update("b1", {37: -70.0, 38: -72.0, 39: -71.0})  # 전 채널 동시 급락
    assert dec.blocked
    assert dec.corrected_rssi[37] == -70.0 + 7.0  # 감쇠 보상
    # 회복: 기준선 부근 복귀 -> 차폐 해제 # ref: P1 Fig.1b
    dec2 = det.update("b1", {37: -60.5, 38: -62.5, 39: -61.5})
    assert not dec2.blocked


def test_threshold_ignores_single_channel_fade():
    det = ThresholdShadowDetector(ShadowParams(shadow_drop_db=4.5))
    rng = np.random.default_rng(0)
    for _ in range(10):
        det.update("b1", {37: -60 + rng.normal(0, 1), 38: -62 + rng.normal(0, 1),
                          39: -61 + rng.normal(0, 1)})
    dec = det.update("b1", {37: -75.0, 38: -62.0, 39: -61.0})  # 채널 37만 페이딩
    assert not dec.blocked  # 다중경로이지 차폐 아님 # ref: P1 §1


def test_threshold_slow_drift_not_shadow():
    """이동에 의한 완만한 감쇠(<임계/창)는 차폐로 오탐하지 않는다."""
    det = ThresholdShadowDetector(ShadowParams(shadow_drop_db=4.5))
    v = {37: -60.0, 38: -62.0, 39: -61.0}
    for _ in range(20):  # 창마다 2dB씩 완만히 감쇠 (멀어지는 보행)
        v = {ch: x - 2.0 for ch, x in v.items()}
        dec = det.update("b1", v)
        assert not dec.blocked


def test_classify_channel_event():
    base = {37: -60.0, 38: -62.0, 39: -61.0}
    assert classify_channel_event({37: -70, 38: -71, 39: -70}, base) == "shadow"
    assert classify_channel_event({37: -75, 38: -62, 39: -61}, base) == "multipath"
    assert classify_channel_event({37: -60.5, 38: -62.2, 39: -61.1}, base) == "normal"


def test_ml_corrector_learns_synthetic_shadow():
    """P1 §2.3 구조 재현: 윈도우 N=10, 3채널, MLP(20,20). 감지율 >80% 기대(P1: 89%)."""
    rng = np.random.default_rng(42)
    params = ShadowParams()
    clean = np.array([-60.0, -62.0, -61.0])
    X, y_rssi, y_blk = [], [], []
    series = {37: [], 38: [], 39: []}
    for t in range(600):
        blocked = (t // 50) % 2 == 1  # 50샘플마다 차폐 on/off
        obs = clean + rng.normal(0, 1.5, 3) - (7.0 if blocked else 0.0)
        for i, ch in enumerate((37, 38, 39)):
            series[ch].append(obs[i])
        w = build_windows(series, n=params.window_size)
        if w is None:
            continue
        X.append(w)
        y_rssi.append(clean + rng.normal(0, 1.5, 3))  # 타깃: 무차폐 실측 분포 # ref: P1 §2.3
        y_blk.append(1 if blocked else 0)
    X, y_rssi, y_blk = np.array(X), np.array(y_rssi), np.array(y_blk)
    n_tr = int(len(X) * 0.7)  # 70/30 분할 # ref: P1 §3
    mc = MlShadowCorrector(params).fit(X[:n_tr], y_rssi[:n_tr], y_blk[:n_tr])
    correct = 0
    for i in range(n_tr, len(X)):
        _, blocked, _ = mc.predict(X[i])
        correct += int(blocked == bool(y_blk[i]))
    acc = correct / (len(X) - n_tr)
    assert acc > 0.8, f"detection accuracy {acc:.2f} (P1 기준 ~0.89)"
