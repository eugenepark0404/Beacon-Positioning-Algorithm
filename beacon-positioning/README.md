# BLE 비콘 실내·지하 측위 — 기본 제반 (캡스톤 트랙1)

핸드폰이 BLE 비콘 신호를 받아 위치를 계산하고, **인체 차폐**를 포함한 오차를
보정하는 측위 파이프라인의 레퍼런스 구현. 트랙2(센서퓨전)·트랙3(실측)·트랙4(Unity
시뮬)가 바로 물려받아 쓸 수 있도록 인터페이스와 데이터 포맷을 고정했다.

## 구성

```
beacon-positioning/
├── ble_positioning/        # Python 코어 (시뮬·실측 공용, 플랫폼 무관)
│   ├── config/             #   캘리브레이션 상수 (하드코딩 금지 — 전부 여기)
│   ├── ingest/             #   Unity JSON/CSV·실측 CSV 로더 (track4-unity-v1)
│   ├── preprocessing/      #   median 창 필터·1D 칼만·MAD 이상치 제거
│   ├── distance/           #   로그-거리 경로손실 (RSSI→거리) + 회귀 캘리브레이션
│   ├── positioning/        #   NLS/선형 다변측량·WCL·확률그리드·KNN·GML(P5)·퍼지WKNN(P9)
│   ├── correction/         #   ★ 인체 차폐 감지·보정 (임계/ANN/잔차) + 다중경로 판별
│   ├── fusion/             #   트랙2 연동: PF 골격(P2 수식)·칼만 골격·PDR 인터페이스
│   ├── output/             #   위치·로그 스키마 (JSON/CSV)
│   └── pipeline.py         #   엔드-투-엔드 파이프라인
├── tests/                  # 단위 테스트 23개 (수식 검산 재현 포함)
├── examples/               # 합성 데이터 생성 + 전체 실행 + 오차 리포트
├── android/                # Kotlin 수신부 (iBeacon+Eddystone 파싱, 공용 포맷 출력)
├── ios/                    # Swift 수신부 (CoreLocation/CoreBluetooth, 제약 문서화)
└── docs/                   # 수식_유도서 · 아키텍처 · 캘리브레이션_가이드 · 검증_리포트
```

## 설치·실행

```bash
pip install numpy scipy scikit-learn pytest
cd beacon-positioning

python -m pytest tests/ -q                      # 단위 테스트 (23개)
PYTHONPATH=. python examples/generate_synthetic.py   # 합성 데이터 생성 (트랙4 포맷)
PYTHONPATH=. python examples/run_pipeline.py         # 파이프라인 + 보정 전/후 오차 표
```

최소 사용 예:
```python
from ble_positioning import PositioningPipeline
from ble_positioning.config.settings import load_config, load_beacon_map
from ble_positioning.ingest.loaders import load_unity_json

cfg = load_config()                      # 또는 load_config("config/site_xxx.json")
beacons = load_beacon_map("beacon_map.json")
samples = load_unity_json("unity_sample.json")
records = PositioningPipeline(cfg, beacons).process(samples)
for r in records:
    print(r.timestamp, r.x, r.y, r.shadow_corrected)
```

## 검증 결과 (합성 데이터, 상세는 docs/검증_리포트.md)

20×12m·비콘 6개·5km/h 보행·노이즈 σ2dB·차폐 7dB(duty 40%)·다중경로 5% 시나리오:

| 구성 | 평균 오차 | 중앙값 |
|------|-----------|--------|
| 보정 전 | 3.39 m | 2.79 m |
| **보정 후 (기본: 잔차 재추정)** | **2.73 m** | **2.17 m** |

평균 오차 **19.5% 개선**. GML(P5)은 꼬리 오차(P90 4.3~4.6 m vs 6.1 m)가 가장 작아
대형 환경·PF 융합 전단용 대안으로 포함 (`positioning_method="gml"`). ANN 차폐
감지기(P1 구조)는 단위 테스트에서 감지 정확도 >80% (P1 보고 89%와 부합) — 실측
학습 데이터 확보 후 1차 보정기로 승격 예정. 절대 오차는 시뮬 조건(placeholder
계수)에 종속 — 실측 캘리브레이션 후 재평가 필수.

## 트랙별 연동 (요약 — 상세는 docs/아키텍처.md)

- **트랙2**: `fusion/interfaces.py`의 `FusionEngine`/`PdrStep` 규격 구현·교체.
  PF 골격(P2 수식·파라미터)과 도면 보정 훅(P5) 제공.
- **트랙3**: `docs/캘리브레이션_가이드.md` 절차로 n·A·차폐dB 실측 → config JSON 주입.
- **트랙4**: 입력 포맷 `track4-unity-v1` 준수 (레퍼런스: `examples/generate_synthetic.py`).
  noise_flag 라벨을 주면 보정 성능 평가가 자동화된다 (`run_pipeline.py`).

## 다음 할 일

1. (트랙3) 비콘 확보 → 캘리브레이션 → placeholder 교체 → 실측 재검증
2. (트랙1) ANN 보정기 실측 학습 → 파이프라인 1차 보정기 승격, 핑거프린트 DB 구축
3. (트랙2) `FusionEngine` 위에 PDR 보폭·방위 추정 연결, PF 파라미터 재튜닝
4. (트랙4) Unity 씬에서 track4-unity-v1 로그 출력 → 동일 리포트로 교차 검증
5. (공통) 좌표계 원점·축 합의 문서 고정, UJIIndoorLoc 등 공개 데이터셋으로 KNN 벤치마크

## 참고 문헌

수식·파라미터의 출처와 열람 수준은 `docs/수식_유도서.md` 표 참조 (P1~P9).
핵심: MDPI Sensors 2020(인체 차폐 ANN), Springer TelSys 2024(BLE+IMU PF, 첨부 PDF),
Riesebos 2022(스마트폰 실시간 IPS), Sensors 2021(BLE RSSI 실측 방법론),
FP-BP arXiv:2504.09905(GML 그리드 MLE), Sensors 2019(퍼지 Type-2 핑거프린팅).
