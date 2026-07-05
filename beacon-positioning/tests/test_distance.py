"""거리 변환 검산: 왕복 일관성 + 유도서 §1.3의 수치 검산 재현."""
import math

from ble_positioning.config.settings import PathLossParams
from ble_positioning.distance.path_loss import LogDistanceModel, fit_log_distance


def test_reference_distance():
    # d = d0 = 1m 에서 RSSI = A  # ref: P1 Eq.(1)
    m = LogDistanceModel(PathLossParams(n=2.0, a_dbm=-59.0))
    assert abs(m.distance_to_rssi(1.0) - (-59.0)) < 1e-9


def test_sign_check_10m():
    # 유도서 §1.3 검산: n=2, A=-59, d=10m -> RSSI=-79
    m = LogDistanceModel(PathLossParams(n=2.0, a_dbm=-59.0))
    assert abs(m.distance_to_rssi(10.0) - (-79.0)) < 1e-9
    assert abs(m.rssi_to_distance(-79.0) - 10.0) < 1e-6


def test_round_trip():
    m = LogDistanceModel(PathLossParams(n=2.7, a_dbm=-61.5))
    for d in (0.5, 1.0, 3.3, 12.0, 40.0):
        assert abs(m.rssi_to_distance(m.distance_to_rssi(d)) - d) < 1e-6


def test_fit_recovers_params():
    true = PathLossParams(n=2.4, a_dbm=-58.0)
    m = LogDistanceModel(true)
    ds = [0.5, 1, 2, 4, 8, 16]
    rs = [m.distance_to_rssi(d) for d in ds]
    n, a = fit_log_distance(ds, rs)
    assert abs(n - 2.4) < 1e-6 and abs(a - (-58.0)) < 1e-6


def test_monotonic_decreasing():
    m = LogDistanceModel(PathLossParams())
    prev = math.inf
    for d in (1, 2, 5, 10, 20):
        r = m.distance_to_rssi(d)
        assert r < prev
        prev = r
