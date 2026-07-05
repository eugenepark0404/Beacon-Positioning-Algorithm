"""전체 파이프라인 실행 예제 + 보정 전/후 오차 리포트.

사용법: python examples/run_pipeline.py
출력: 보정 전 vs 후 평균/중앙값/RMS 오차(m) 표 + docs/검증_리포트.md
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from ble_positioning.config.settings import PipelineConfig, load_beacon_map
from ble_positioning.ingest.loaders import load_unity_json
from ble_positioning.output.writers import write_positions_csv
from ble_positioning.pipeline import PositioningPipeline

HERE = Path(__file__).parent
DATA = HERE / "data"


def error_stats(records):
    errs = np.array([r.error_m for r in records if r.error_m is not None])
    return {
        "n": int(errs.size),
        "mean": float(errs.mean()),
        "median": float(np.median(errs)),
        "rms": float(np.sqrt((errs ** 2).mean())),
        "p90": float(np.percentile(errs, 90)),
        "within_1m_pct": float((errs <= 1.0).mean() * 100),  # P2의 ±1m 지표
    }


def _variant(samples, beacons, *, correct, channel_rule=False, residual_iters=2,
             residual_th=1.5, method="nls"):
    cfg = PipelineConfig()
    cfg.positioning_method = method
    cfg.shadow.use_channel_rule = channel_rule
    cfg.shadow.residual_iters = residual_iters
    cfg.shadow.residual_thresh_m = residual_th
    pipe = PositioningPipeline(cfg, beacons, correct_shadowing=correct)
    recs = pipe.process(samples)
    return recs, error_stats(recs)


def main():
    if not (DATA / "unity_sample.json").exists():
        from generate_synthetic import generate
        generate(out_dir=DATA)

    samples = load_unity_json(DATA / "unity_sample.json")
    beacons = load_beacon_map(DATA / "beacon_map.json")

    variants = {
        "보정 전 (raw)":        dict(correct=False),
        "채널 규칙만 (P1 [9])": dict(correct=True, channel_rule=True, residual_iters=0),
        "잔차 보정만 (기본)":   dict(correct=True),
        "채널+잔차 결합":       dict(correct=True, channel_rule=True),
        "GML (P5) 보정 전":     dict(correct=False, method="gml"),
        "GML (P5) + 잔차 보정": dict(correct=True, method="gml"),
    }
    results = {}
    for label, kw in variants.items():
        recs, stats = _variant(samples, beacons, **kw)
        results[label] = (recs, stats)
    write_positions_csv(results["보정 전 (raw)"][0], DATA / "positions_raw.csv")
    write_positions_csv(results["잔차 보정만 (기본)"][0], DATA / "positions_corrected.csv")

    hdr = f"{'구성':24s} {'N':>5s} {'평균(m)':>8s} {'중앙값(m)':>9s} {'RMS(m)':>8s} {'P90(m)':>8s} {'<=1m(%)':>8s}"
    print(hdr)
    for label, (_, s) in results.items():
        print(f"{label:24s} {s['n']:5d} {s['mean']:8.3f} {s['median']:9.3f} "
              f"{s['rms']:8.3f} {s['p90']:8.3f} {s['within_1m_pct']:8.1f}")

    s0 = results["보정 전 (raw)"][1]
    s1 = results["잔차 보정만 (기본)"][1]
    impr = (1 - s1["mean"] / s0["mean"]) * 100
    print(f"\n기본 구성(잔차 보정) 평균 오차 개선율: {impr:.1f}%")
    (DATA / "report.json").write_text(json.dumps(
        {k: v[1] for k, v in results.items()} | {"improvement_pct": impr},
        indent=2, ensure_ascii=False))

    # 마크다운 검증 리포트
    lines = ["# 합성 데이터 검증 리포트 (자동 생성)", "",
             "생성: `examples/run_pipeline.py` — 시나리오: 20x12 m, 비콘 6개, 5 km/h 순회,",
             "노이즈 sigma=2 dB, 차폐 7 dB(3.3 s 이벤트, duty 40%, 3개 비콘), 다중경로 5%.",
             "(유도서 §6 근거: P1 Eq.(1), P2 §4.3, P3 §III-A/Table II)", "",
             "| 구성 | N | 평균(m) | 중앙값(m) | RMS(m) | P90(m) | <=1m(%) |",
             "|------|---|--------|----------|--------|--------|---------|"]
    for label, (_, s) in results.items():
        lines.append(f"| {label} | {s['n']} | {s['mean']:.3f} | {s['median']:.3f} | "
                     f"{s['rms']:.3f} | {s['p90']:.3f} | {s['within_1m_pct']:.1f} |")
    lines += ["", f"**기본 구성(잔차 보정) 평균 오차 개선율: {impr:.1f}%**", "",
              "관찰:",
              "- 채널 규칙(P1 선행연구 [9]의 임계 방식)은 이동 수신기에서 재현율이 낮다.",
              "  거리 변화 자체가 3채널을 동시에 감쇠시켜 차폐와 구분이 어렵기 때문이며,",
              "  P1이 임계 방식 대신 ANN을 제안한 이유와 부합한다.",
              "- 잔차 기반 반복 재추정(강건 추정)은 차폐의 '거리 과대추정' 단방향 바이어스를",
              "  이용하므로 이동 중에도 유효하다.",
              "- ANN 보정기(MlShadowCorrector, P1 §2.3 구조)는 tests/test_correction.py 의",
              "  합성 학습에서 차폐 감지 정확도 >80% (P1 보고치 89%와 부합). 실측(트랙3) 학습",
              "  데이터 확보 후 파이프라인 1차 보정기로 승격 예정.",
              "- GML(P5)은 로그정규 노이즈 통계에 맞는 우도 + 볼록껍질 제약 덕에 꼬리 오차",
              "  (P90/RMS)가 가장 작다. 평균은 NLS+잔차가 우세 — 비콘 6개 소형 환경 기준이며,",
              "  비콘이 많고 넓은 역사 환경·PF 융합 전단(front-end)에는 GML이 적합 (P5의 용법).",
              "  기본값은 NLS+잔차 유지, cfg.positioning_method='gml' 로 전환 가능."]
    (Path(__file__).parent.parent / "docs" / "검증_리포트.md").write_text(
        "\n".join(lines), encoding="utf-8")
    print("리포트 저장: docs/검증_리포트.md")
    return results


if __name__ == "__main__":
    main()
