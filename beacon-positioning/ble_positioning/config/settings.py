"""캘리브레이션 상수·비콘 좌표 맵 · 필터 파라미터 (하드코딩 금지 원칙).

기본값의 출처는 docs/수식_유도서.md §7 파라미터 요약표.
"PLACEHOLDER" 표기가 있는 값은 트랙3 실측 후 반드시 교체한다.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, Tuple, Optional


@dataclass
class PathLossParams:
    """로그-거리 경로손실 모델 계수. # ref: P1 Eq.(1), P3 Eq.(1)-(3)"""
    n: float = 2.0            # PLACEHOLDER: 경로손실지수 (P3 최적 1.8~2.4, 트랙3 실측 교체)
    a_dbm: float = -59.0      # PLACEHOLDER: RSSI(d0=1m) [dBm] (P3 실측 -54~-58)
    d0_m: float = 1.0         # 기준 거리 [m]
    max_range_m: float = 50.0 # 물리적으로 유효한 최대 거리 clip


@dataclass
class FilterParams:
    """RSSI 안정화 필터. # ref: P3 §III-B/§V-A, P4 §2.3.4"""
    window_size: int = 10          # P3 최적 윈도우
    method: str = "median"         # P3: median > mode >> mean
    kalman_q: float = 1.0          # PLACEHOLDER: 공정잡음 (보행 시 RSSI 변화율 ~3dB/s 대응, 트랙3 튜닝)
    kalman_r: float = 4.0          # 측정잡음 ~ P3 실측 분산 (sigma 1.5~2.6dB)
    outlier_mad_k: float = 3.0     # MAD 이상치 임계


@dataclass
class ShadowParams:
    """인체 차폐 감지·보정. # ref: P1 §2.2-2.3, P3 Table II"""
    window_size: int = 10          # P1 §2.3 슬라이딩 윈도우 N=10
    sigma_k: float = 1.0           # P1 [9] 임계값 (k·sigma) — ANN 학습 라벨링용
    shadow_drop_db: float = 4.5    # PLACEHOLDER: 차폐 진입 급락 임계 [dB/창] (P1 Fig.1b, 트랙3 실측 교체)
    shadow_atten_db: float = 7.0   # PLACEHOLDER: 차폐 감쇠 보상 [dB] (P3 LOS/NLOS 차 6~9dB, 트랙3 실측 교체)
    mlp_hidden: Tuple[int, int] = (20, 20)  # P1 §2.3.1 MLP 구조
    channels: Tuple[int, ...] = (37, 38, 39)  # BLE 광고 채널 (P1 §2.1)
    multipath_spread_db: float = 6.0  # 채널 간 편차 임계 (다중경로 판별, P1 원리)
    residual_thresh_m: float = 1.5    # 측위 잔차 기반 차폐 의심 임계 [m] (엔지니어링 확장, 유도서 §3.4)
    residual_iters: int = 2           # 잔차 재추정 반복 횟수
    # 채널 규칙(P1 [9] 임계 방식) 기반 '보정' 사용 여부. 정지/저속 수신기에선 유효하나
    # 보행 중에는 거리 변화도 전 채널을 동시 감쇠시켜 오탐이 생긴다(검증 리포트 §분해 실험).
    # 학습된 MlShadowCorrector(P1 본논문 ANN)가 준비되면 그것을 우선 사용할 것.
    use_channel_rule: bool = False


@dataclass
class ParticleFilterParams:
    """BLE+IMU 융합 PF. # ref: P2 Eq.(9)-(28)"""
    n_particles: int = 10_000      # P2 §5.6 (30k 대비 정확도 손실 <1%)
    sigma_xy: float = 0.5          # P2 Eq.(15)
    sigma_v: float = 1.0           # P2 Eq.(16)
    sigma_alpha: float = 0.3       # P2 Eq.(17)
    b_v: float = 0.3               # P2 Eq.(20) IMU 우도 베이스라인
    sigma_v_like: float = 0.7      # P2 Eq.(21)
    b_w: float = 0.1               # P2 Eq.(24) BLE 우도 베이스라인
    sigma_ble_m: float = 2.0       # PLACEHOLDER: BLE 단독 측위 오차 sigma [m]


@dataclass
class GmlParams:
    """GML 그리드 최대우도 측위. # ref: P5 §III Eq.(9)-(22)"""
    grid_step_m: float = 0.3       # P5 Table: virtual grid interval 0.3 m
    top_n: int = 6                 # RSSI 상위 N 비콘 선택 (P5 Eq.(9), N>=3; 합성 검증에서 6 최적)
    eta: float = 0.1               # η=σ̂/(10n) (P5 Eq.(12); σ̂=2dB, n=2) PLACEHOLDER
    d0_manhattan_m: float = 6.0    # 후보 격자 반경 (P5 Eq.(20)) PLACEHOLDER
    avg_n: int = 3                 # 시간 평활 창 (P5 Eq.(22))
    restrict_hull: bool = True     # 볼록껍질 제약 (밀집 배치 시, P5 Eq.(20)/(21))


@dataclass
class PipelineConfig:
    path_loss: PathLossParams = field(default_factory=PathLossParams)
    filter: FilterParams = field(default_factory=FilterParams)
    shadow: ShadowParams = field(default_factory=ShadowParams)
    pf: ParticleFilterParams = field(default_factory=ParticleFilterParams)
    gml: GmlParams = field(default_factory=GmlParams)
    positioning_method: str = "nls"     # nls | linear | wcl | grid | gml | knn
    wcl_g: float = 2.5                  # P3 §V-B 가중지수 2.0~3.5
    grid_c: float = 1.0                 # P3 Eq.(8) 첨예도
    grid_step_m: float = 0.25
    scan_window_s: float = 1.0          # 스캔 집계 창 (P3: 0.5~2.0s 권장, Faragher&Harle 재인용)
    per_beacon_path_loss: Dict[str, PathLossParams] = field(default_factory=dict)

    def path_loss_for(self, beacon_id: str) -> PathLossParams:
        return self.per_beacon_path_loss.get(beacon_id, self.path_loss)

    def to_json(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False))


def load_config(path: Optional[str | Path] = None) -> PipelineConfig:
    """JSON 파일에서 설정 로드. 없으면 문헌 기본값."""
    cfg = PipelineConfig()
    if path is None:
        return cfg
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if "path_loss" in raw:
        cfg.path_loss = PathLossParams(**raw["path_loss"])
    if "filter" in raw:
        cfg.filter = FilterParams(**raw["filter"])
    if "shadow" in raw:
        sh = dict(raw["shadow"])
        if "mlp_hidden" in sh:
            sh["mlp_hidden"] = tuple(sh["mlp_hidden"])
        if "channels" in sh:
            sh["channels"] = tuple(sh["channels"])
        cfg.shadow = ShadowParams(**sh)
    if "pf" in raw:
        cfg.pf = ParticleFilterParams(**raw["pf"])
    if "gml" in raw:
        cfg.gml = GmlParams(**raw["gml"])
    for key in ("positioning_method", "wcl_g", "grid_c", "grid_step_m", "scan_window_s"):
        if key in raw:
            setattr(cfg, key, raw[key])
    for bid, params in raw.get("per_beacon_path_loss", {}).items():
        cfg.per_beacon_path_loss[bid] = PathLossParams(**params)
    return cfg


def load_beacon_map(path: str | Path) -> Dict[str, Tuple[float, float]]:
    """비콘 좌표 맵 로드. JSON: {"beacon_id": [x, y], ...} (단위 m, 트랙4 좌표계와 합의)"""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return {k: (float(v[0]), float(v[1])) for k, v in raw.items()}
