"""삼변측량/WCL/그리드/KNN 검산 — 유도서 §2 수치 검산 재현."""
import numpy as np

from ble_positioning.positioning.estimators import (
    trilaterate_linear, trilaterate_nls, weighted_centroid, grid_probability,
    FingerprintDB, KnnEstimator,
)

BEACONS = {"b1": (0.0, 0.0), "b2": (10.0, 0.0), "b3": (0.0, 10.0)}


def _dists(p, beacons=BEACONS):
    return {b: float(np.hypot(x - p[0], y - p[1])) for b, (x, y) in beacons.items()}


def test_linear_exact():
    # 유도서 §2.1 검산 케이스: (3,4)
    est = trilaterate_linear(BEACONS, _dists((3.0, 4.0)))
    assert est is not None
    assert abs(est.x - 3.0) < 1e-9 and abs(est.y - 4.0) < 1e-9


def test_nls_exact():
    est = trilaterate_nls(BEACONS, _dists((7.2, 2.5)))
    assert abs(est.x - 7.2) < 1e-6 and abs(est.y - 2.5) < 1e-6


def test_nls_noisy_better_than_2m():
    rng = np.random.default_rng(1)
    p = (4.0, 6.0)
    d = {b: v * (1 + rng.normal(0, 0.05)) for b, v in _dists(p).items()}
    est = trilaterate_nls(BEACONS, d, weight_g=1.0)
    assert np.hypot(est.x - p[0], est.y - p[1]) < 2.0


def test_wcl_inside_convex_hull():
    est = weighted_centroid(BEACONS, _dists((2.0, 2.0)), g=2.5)
    assert 0 <= est.x <= 10 and 0 <= est.y <= 10


def test_wcl_fallback_two_beacons():
    d = {"b1": 5.0, "b2": 5.0}
    est = weighted_centroid(BEACONS, d, g=2.5)
    assert est is not None and est.n_beacons == 2


def test_grid_probability():
    est = grid_probability(BEACONS, _dists((3.0, 4.0)), (-1, -1, 11, 11), step=0.25, c=1.0)
    assert np.hypot(est.x - 3.0, est.y - 4.0) < 0.5


def test_knn_recovers_grid_point():
    # 4x4 격자 핑거프린트 -> 질의 벡터가 참조점과 같으면 그 점 복원
    from ble_positioning.config.settings import PathLossParams
    from ble_positioning.distance.path_loss import LogDistanceModel
    m = LogDistanceModel(PathLossParams())
    db = FingerprintDB(list(BEACONS))
    for x in range(0, 10, 3):
        for y in range(0, 10, 3):
            fp = {b: m.distance_to_rssi(np.hypot(bx - x, by - y) or 0.1)
                  for b, (bx, by) in BEACONS.items()}
            db.add((x, y), fp)
    q = {b: m.distance_to_rssi(np.hypot(bx - 3, by - 6) or 0.1)
         for b, (bx, by) in BEACONS.items()}
    est = KnnEstimator(db, k=3, weighted=True).estimate(q)
    assert np.hypot(est.x - 3, est.y - 6) < 3.0


def test_gml_exact_recovery():
    """GML: 무노이즈 거리 -> 참 위치 격자 근방 복원. # ref: P5 Eq.(19)"""
    from ble_positioning.positioning.gml import GmlEstimator
    est = GmlEstimator(BEACONS, (-1, -1, 11, 11), grid_step=0.25, avg_n=1)
    out = est.estimate(_dists((3.0, 4.0)))
    assert np.hypot(out.x - 3.0, out.y - 4.0) < 0.3


def test_gml_log_domain_beats_linear_domain_under_lognormal_noise():
    """P5 §III 논지 재현: 로그정규 노이즈에서 log-거리 우도(GML)가
    선형 거리 잔차(NLS)보다 평균 오차가 작거나 비슷해야 한다."""
    from ble_positioning.positioning.gml import GmlEstimator
    rng = np.random.default_rng(3)
    n, sigma = 2.0, 2.0
    eta = sigma / (10 * n)  # P5 Eq.(12)
    errs_gml, errs_nls = [], []
    for trial in range(40):
        p = rng.uniform(2, 8, 2)
        true_d = {b: float(np.hypot(x - p[0], y - p[1])) for b, (x, y) in BEACONS.items()}
        # RSSI 노이즈 -> 거리의 로그정규 왜곡 (P5 Eq.(11)-(13))
        noisy = {b: d * 10 ** (rng.normal(0, sigma) / (10 * n)) for b, d in true_d.items()}
        g = GmlEstimator(BEACONS, (-1, -1, 11, 11), grid_step=0.25, eta=eta, avg_n=1)
        e1 = g.estimate(noisy)
        e2 = trilaterate_nls(BEACONS, noisy, weight_g=1.0)
        errs_gml.append(np.hypot(e1.x - p[0], e1.y - p[1]))
        errs_nls.append(np.hypot(e2.x - p[0], e2.y - p[1]))
    assert np.mean(errs_gml) <= np.mean(errs_nls) * 1.05


def test_fuzzy_wknn_recovers_position():
    """FuzzyWknnEstimator: 격자 핑거프린트에서 질의점 복원. # ref: P9 Eq.(4)-(5)"""
    from ble_positioning.config.settings import PathLossParams
    from ble_positioning.distance.path_loss import LogDistanceModel
    from ble_positioning.positioning.fuzzy import FuzzyWknnEstimator
    m = LogDistanceModel(PathLossParams())
    db = FingerprintDB(list(BEACONS))
    for x in range(0, 11, 2):
        for y in range(0, 11, 2):
            fp = {b: m.distance_to_rssi(max(np.hypot(bx - x, by - y), 0.1))
                  for b, (bx, by) in BEACONS.items()}
            db.add((x, y), fp)
    q = {b: m.distance_to_rssi(max(np.hypot(bx - 4, by - 6), 0.1))
         for b, (bx, by) in BEACONS.items()}
    est = FuzzyWknnEstimator(db, BEACONS, k=4, type2=True).estimate(q)
    assert np.hypot(est.x - 4, est.y - 6) < 2.5
