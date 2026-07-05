"""엔드-투-엔드 측위 파이프라인: 수신 → 전처리 → (차폐 보정) → 거리 → 위치 → 출력.

데이터 흐름은 docs/아키텍처.md 참조. 각 단계 수식 출처는 docs/수식_유도서.md.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from .config.settings import PipelineConfig
from .correction.shadowing import ThresholdShadowDetector
from .distance.path_loss import LogDistanceModel
from .ingest.loaders import RssiSample, group_scan_windows
from .output.writers import PositionRecord
from .positioning.estimators import (
    trilaterate_linear, trilaterate_nls, weighted_centroid, grid_probability,
)
from .positioning.gml import GmlEstimator
from .preprocessing.filters import SlidingWindowFilter, RssiKalman1D, aggregate_by_beacon


class PositioningPipeline:
    def __init__(self, config: PipelineConfig,
                 beacon_map: Dict[str, Tuple[float, float]],
                 correct_shadowing: bool = True,
                 bounds: Optional[Tuple[float, float, float, float]] = None) -> None:
        self.cfg = config
        self.beacons = beacon_map
        self.correct_shadowing = correct_shadowing
        xs = [p[0] for p in beacon_map.values()]
        ys = [p[1] for p in beacon_map.values()]
        self.bounds = bounds or (min(xs) - 2, min(ys) - 2, max(xs) + 2, max(ys) + 2)
        self.window_filter = SlidingWindowFilter(config.filter.window_size,
                                                 config.filter.method)   # ref: P3 §III-B
        self.kalman = RssiKalman1D(config.filter.kalman_q, config.filter.kalman_r)  # ref: P4 §2.3.4
        self.shadow = ThresholdShadowDetector(config.shadow)             # ref: P1
        self._models: Dict[str, LogDistanceModel] = {}
        self.gml = GmlEstimator(beacon_map, self.bounds,
                                grid_step=config.gml.grid_step_m,
                                top_n=config.gml.top_n, eta=config.gml.eta,
                                d0_manhattan=config.gml.d0_manhattan_m,
                                avg_n=config.gml.avg_n,
                                restrict_hull=config.gml.restrict_hull)  # ref: P5 §III

    def _model(self, beacon_id: str) -> LogDistanceModel:
        if beacon_id not in self._models:
            self._models[beacon_id] = LogDistanceModel(self.cfg.path_loss_for(beacon_id))
        return self._models[beacon_id]

    # ---- 단계별 처리 ----
    def _shadow_correct(self, window_samples: List[RssiSample]) -> Tuple[List[RssiSample], set]:
        """채널 정보가 있으면 3채널 규칙(P1)으로 차폐 감지·보정."""
        by_beacon_ch: Dict[str, Dict[int, List[float]]] = defaultdict(lambda: defaultdict(list))
        has_channel = False
        for s in window_samples:
            if s.channel is not None:
                has_channel = True
                by_beacon_ch[s.beacon_id][s.channel].append(s.rssi)
        if not has_channel:
            return window_samples, set()
        adjust: Dict[str, float] = {}
        for bid, chans in by_beacon_ch.items():
            rep = {ch: sum(v) / len(v) for ch, v in chans.items()}
            dec = self.shadow.update(bid, rep)
            if dec.blocked:
                # 보정량 = 보상 후 - 보상 전 (전 채널 공통) # ref: P1 §2.3 / 유도서 §3.4
                any_ch = next(iter(rep))
                adjust[bid] = dec.corrected_rssi[any_ch] - rep[any_ch]
        if not adjust:
            return window_samples, set()
        out = []
        for s in window_samples:
            if s.beacon_id in adjust:
                s = RssiSample(s.timestamp, s.beacon_id, s.rssi + adjust[s.beacon_id],
                               s.channel, s.x_true, s.y_true, s.noise_flag)
            out.append(s)
        return out, set(adjust)

    def _residual_refine(self, dists: Dict[str, float], rep: Dict[str, float], est,
                         skip: set = frozenset()):
        """잔차 기반 차폐/NLoS 2차 보정 (IRLS 유사 반복 재추정).

        초기 위치 추정 후, '측정 거리 >> 추정 위치까지의 기하 거리'인 비콘은
        신호가 추가 감쇠(차폐/NLoS)된 것으로 보고 RSSI에 감쇠 보상 후 재적합.
        근거: 차폐는 RSSI를 낮춰 거리를 '과대추정'시키는 단방향 바이어스 (P1 §2.2,
        P3 Table II의 NLOS 추세선). 반복 재가중은 표준 강건 추정 기법 — 논문 수식
        아님을 명시(유도서 §3.4). 임계·보상량은 config (트랙3 실측 교체).
        """
        changed_any = False
        for _ in range(self.cfg.shadow.residual_iters):
            changed = False
            for b in list(dists):
                if b in skip:      # 채널 규칙으로 이미 보상된 비콘 — 이중 보상 방지
                    continue
                bx, by = self.beacons[b]
                pred = ((bx - est.x) ** 2 + (by - est.y) ** 2) ** 0.5
                if dists[b] - pred > self.cfg.shadow.residual_thresh_m:
                    dists[b] = self._model(b).rssi_to_distance(
                        rep[b] + self.cfg.shadow.shadow_atten_db)
                    changed = changed_any = True
            if not changed:
                break
            if self.cfg.positioning_method == "gml":
                new_est = self.gml.estimate(dists, rep)      # ref: P5 Eq.(19)
            else:
                new_est = trilaterate_nls(self.beacons, dists, weight_g=1.0, x0=(est.x, est.y))
            if new_est is None:
                break
            est = new_est
        return est, changed_any

    def _estimate(self, dists: Dict[str, float], rep: Dict[str, float] = None):
        m = self.cfg.positioning_method
        est = None
        if m == "gml":       # ref: P5 Eq.(19)-(22)
            est = self.gml.estimate(dists, rep)
        elif m == "linear":
            est = trilaterate_linear(self.beacons, dists)
        elif m == "grid":
            est = grid_probability(self.beacons, dists, self.bounds,
                                   self.cfg.grid_step_m, self.cfg.grid_c)
        elif m == "wcl":
            est = weighted_centroid(self.beacons, dists, self.cfg.wcl_g)
        else:  # "nls" 기본 # ref: P1 §2
            est = trilaterate_nls(self.beacons, dists, weight_g=1.0)
        if est is None:  # 삼변측량 불능(비콘<3, 특이) → WCL fallback # ref: P3 §III-D.1 case 3
            est = weighted_centroid(self.beacons, dists, self.cfg.wcl_g)
        return est

    def process(self, samples: List[RssiSample]) -> List[PositionRecord]:
        records: List[PositionRecord] = []
        for t_mid, win in group_scan_windows(samples, self.cfg.scan_window_s):
            ch_corrected: set = set()
            if self.correct_shadowing and self.cfg.shadow.use_channel_rule:
                win, ch_corrected = self._shadow_correct(win)
            corrected = bool(ch_corrected)
            # 필터링: 창 집계(중앙값+MAD) 후 칼만 스무딩
            rep = aggregate_by_beacon(win, self.cfg.filter.outlier_mad_k)
            rep = {b: self.kalman.update(b, v) for b, v in rep.items()}
            dists = {b: self._model(b).rssi_to_distance(v)
                     for b, v in rep.items() if b in self.beacons}
            if len(dists) < 1:
                continue
            est = self._estimate(dists, rep)
            if est is None:
                continue
            if self.correct_shadowing and est.method in ("nls", "linear", "gml") and len(dists) >= 3:
                est, refined = self._residual_refine(dists, rep, est, skip=ch_corrected)
                corrected = corrected or refined
            truth = [(s.x_true, s.y_true) for s in win if s.x_true is not None]
            xt = sum(p[0] for p in truth) / len(truth) if truth else None
            yt = sum(p[1] for p in truth) / len(truth) if truth else None
            records.append(PositionRecord(
                timestamp=t_mid, x=est.x, y=est.y, method=est.method,
                n_beacons=est.n_beacons, shadow_corrected=corrected,
                residual=est.residual, x_true=xt, y_true=yt))
        return records
