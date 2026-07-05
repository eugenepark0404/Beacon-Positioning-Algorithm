"""데이터 로더 — Unity(트랙4) JSON/CSV와 실측 CSV를 동일 인터페이스로.

고정 포맷 (아키텍처.md §데이터 포맷):
  CSV 컬럼: timestamp,beacon_id,rssi[,channel][,x_true][,y_true][,noise_flag]
  Unity JSON: {"meta": {...}, "samples": [{"t":..,"beacon_id":..,"rssi":..,
               "channel":..,"noise_flag":..,"x_true":..,"y_true":..}, ...]}
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, List, Optional, Tuple


@dataclass
class RssiSample:
    timestamp: float            # [s] (epoch 또는 시뮬 상대시간)
    beacon_id: str
    rssi: float                 # [dBm]
    channel: Optional[int] = None       # 37|38|39, 미상이면 None
    x_true: Optional[float] = None      # 정답 좌표 (시뮬/평가용)
    y_true: Optional[float] = None
    noise_flag: Optional[str] = None    # 트랙4 주입 오차 라벨 (shadow|multipath|none)


def _opt_float(v) -> Optional[float]:
    if v is None or v == "" or v == "None":
        return None
    return float(v)


def load_csv(path: str | Path) -> List[RssiSample]:
    samples: List[RssiSample] = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ch = row.get("channel")
            samples.append(RssiSample(
                timestamp=float(row["timestamp"]),
                beacon_id=str(row["beacon_id"]),
                rssi=float(row["rssi"]),
                channel=int(ch) if ch not in (None, "", "None") else None,
                x_true=_opt_float(row.get("x_true")),
                y_true=_opt_float(row.get("y_true")),
                noise_flag=row.get("noise_flag") or None,
            ))
    samples.sort(key=lambda s: s.timestamp)
    return samples


def load_unity_json(path: str | Path) -> List[RssiSample]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    entries = raw["samples"] if isinstance(raw, dict) else raw
    samples = [RssiSample(
        timestamp=float(e.get("t", e.get("timestamp"))),
        beacon_id=str(e["beacon_id"]),
        rssi=float(e["rssi"]),
        channel=e.get("channel"),
        x_true=_opt_float(e.get("x_true")),
        y_true=_opt_float(e.get("y_true")),
        noise_flag=e.get("noise_flag"),
    ) for e in entries]
    samples.sort(key=lambda s: s.timestamp)
    return samples


def group_scan_windows(samples: List[RssiSample], window_s: float,
                       ) -> Iterator[Tuple[float, List[RssiSample]]]:
    """시간창 단위 집계 (P3: 0.5~2.0s 창 권장). yield (창 중심시각, 창 내 샘플들)."""
    if not samples:
        return
    t0 = samples[0].timestamp
    bucket: List[RssiSample] = []
    edge = t0 + window_s
    for s in samples:
        if s.timestamp >= edge:
            if bucket:
                yield (edge - window_s / 2.0, bucket)
            bucket = []
            while s.timestamp >= edge:
                edge += window_s
        bucket.append(s)
    if bucket:
        yield (edge - window_s / 2.0, bucket)
