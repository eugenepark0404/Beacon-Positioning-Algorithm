"""합성 데이터 생성기 — 트랙4 Unity 포맷과 동일한 JSON/CSV 시계열 생성.

# ref: 유도서 §6 (P2 §4.1 시뮬레이터 개념 + P1 Eq.(1) + P3 실측 통계)
알려진 비콘 배치 → 궤적 → 이상적 RSSI → 노이즈/차폐/다중경로 주입.
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import numpy as np

from ble_positioning.config.settings import PathLossParams
from ble_positioning.distance.path_loss import LogDistanceModel

# 가상 승강장 20 x 12 m, 비콘 6개 (기둥/벽 배치 가정)
BEACONS = {
    "B01": (0.0, 0.0), "B02": (10.0, 0.0), "B03": (20.0, 0.0),
    "B04": (0.0, 12.0), "B05": (10.0, 12.0), "B06": (20.0, 12.0),
}
WAYPOINTS = [(2.0, 2.0), (18.0, 2.0), (18.0, 10.0), (2.0, 10.0), (2.0, 2.0)]
SPEED_MPS = 1.39          # 5 km/h # ref: P2 §4.2, P3 §IV-A.2 보행속도
SAMPLE_HZ = 10.0          # 3채널 x ~3.3Hz 상당
SIGMA_NOISE_DB = 2.0      # ref: P3 §III-A 실측 1.49~2.55 dB
SHADOW_ATTEN_DB = 7.0     # ref: P3 Table II LOS/NLOS 차 6~9dB (트랙3 실측 교체 대상)
SHADOW_DUTY = 0.4         # 오차 주입률 40% # ref: P2 §4.3 Setup C
CHANNELS = (37, 38, 39)


def _trajectory(t: float):
    seg_lens, total = [], 0.0
    for a, b in zip(WAYPOINTS[:-1], WAYPOINTS[1:]):
        L = math.dist(a, b)
        seg_lens.append(L)
        total += L
    s = (t * SPEED_MPS) % total
    for (a, b), L in zip(zip(WAYPOINTS[:-1], WAYPOINTS[1:]), seg_lens):
        if s <= L:
            f = s / L
            return (a[0] + f * (b[0] - a[0]), a[1] + f * (b[1] - a[1]))
        s -= L
    return WAYPOINTS[-1]


def generate(duration_s: float = 120.0, seed: int = 7, out_dir: str | Path = "."):
    rng = np.random.default_rng(seed)
    model = LogDistanceModel(PathLossParams(n=2.0, a_dbm=-59.0))
    rows = []
    n_steps = int(duration_s * SAMPLE_HZ)
    # 차폐 이벤트: 3.3초 비중첩 구간 + 최소 2초 간격, duty ~40% # ref: P2 §4.3 Setup C
    # (사람이 지나가며 막았다 벗어나는 급락-회복 패턴, P1 Fig.1b·§2.2)
    shadow_on = np.zeros(n_steps, dtype=bool)
    ev, gap = int(3.3 * SAMPLE_HZ), int(2.0 * SAMPLE_HZ)
    cursor = rng.integers(0, gap)
    while cursor + ev < n_steps and shadow_on.mean() < SHADOW_DUTY:
        shadow_on[cursor:cursor + ev] = True
        cursor += ev + gap + int(rng.integers(0, gap))
    # 차폐는 특정 비콘 부분집합(사람이 막는 방향)에만 적용
    shadow_targets = rng.choice(list(BEACONS), size=3, replace=False)

    for i in range(n_steps):
        t = i / SAMPLE_HZ
        x, y = _trajectory(t)
        ch = CHANNELS[i % 3]  # 채널 로테이션 (P1: 50ms 간격 채널 전환 관례)
        for bid, (bx, by) in BEACONS.items():
            d = max(math.dist((x, y), (bx, by)), 0.1)
            rssi = model.distance_to_rssi(d) + rng.normal(0, SIGMA_NOISE_DB)  # ref: P1 Eq.(1)
            flag = "none"
            if shadow_on[i] and bid in shadow_targets:
                rssi -= SHADOW_ATTEN_DB + rng.normal(0, 1.0)   # 전 채널 공통 감쇠 # ref: P1 §2.2
                flag = "shadow"
            elif rng.random() < 0.05:
                rssi -= rng.uniform(2.0, 8.0)                   # 일부 채널만 다중경로 # ref: P1 §1
                flag = "multipath"
            rows.append({"t": round(t, 3), "beacon_id": bid, "rssi": round(float(rssi), 2),
                         "channel": ch, "x_true": round(x, 3), "y_true": round(y, 3),
                         "noise_flag": flag})

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "unity_sample.json").write_text(
        json.dumps({"meta": {"format": "track4-unity-v1", "beacons": BEACONS,
                             "shadow_targets": list(shadow_targets)},
                    "samples": rows}, indent=1), encoding="utf-8")
    with open(out_dir / "synthetic_sample.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["timestamp", "beacon_id", "rssi", "channel",
                                          "x_true", "y_true", "noise_flag"])
        w.writeheader()
        for r in rows:
            w.writerow({"timestamp": r["t"], **{k: r[k] for k in
                        ("beacon_id", "rssi", "channel", "x_true", "y_true", "noise_flag")}})
    (out_dir / "beacon_map.json").write_text(json.dumps(BEACONS, indent=2))
    return out_dir


if __name__ == "__main__":
    d = generate(out_dir=Path(__file__).parent / "data")
    print(f"generated: {d}")
