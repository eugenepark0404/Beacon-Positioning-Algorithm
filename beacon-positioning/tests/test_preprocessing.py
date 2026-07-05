import numpy as np

from ble_positioning.preprocessing.filters import (
    SlidingWindowFilter, RssiKalman1D, remove_outliers_mad,
)


def test_median_window():
    f = SlidingWindowFilter(window_size=5, method="median")
    out = [f.update("b1", v) for v in (-60, -61, -90, -60, -61)]
    assert out[-1] == -61  # 스파이크(-90) 억제


def test_kalman_smooths_noise():
    kf = RssiKalman1D(q=0.05, r=4.0)
    rng = np.random.default_rng(0)
    est = [kf.update("b1", -60 + rng.normal(0, 2)) for _ in range(200)]
    assert np.std(est[50:]) < 2.0  # 원 잡음 sigma=2보다 작아야


def test_mad_outlier_removal():
    vals = [-60.0, -61.0, -60.5, -59.5, -95.0]
    out = remove_outliers_mad(vals, k=3.0)
    assert -95.0 not in out and len(out) == 4
