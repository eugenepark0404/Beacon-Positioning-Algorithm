# Android BLE 수신부 (트랙1 — 수신 파이프라인)

핸드폰이 비콘 광고 패킷을 받아 RSSI를 샘플링하고, 코어 알고리즘(`ble_positioning/`)
입력 포맷(JSON/CSV)으로 내보내는 최소 구현.

## 구조

| 파일 | 역할 |
|------|------|
| `BeaconScanner.kt` | `BluetoothLeScanner` 저지연 스캔, 콜백에서 RSSI 샘플 생성 |
| `BeaconParser.kt` | iBeacon(제조사 데이터 0x004C) + Eddystone(서비스 0xFEAA) 파싱 |
| `RssiExporter.kt` | 공용 CSV/JSON 포맷 내보내기 (iOS와 동일 스키마) |
| `PositioningBridge.kt` | 온디바이스 측위 연동 인터페이스 (코어 이식 지점) |
| `MainActivity.kt` | 권한 요청 + 스캔 시작/정지 + 내보내기 데모 |

## 권한 (API 31+)

- `BLUETOOTH_SCAN` (+ `neverForLocation` 미사용 — 측위 목적이므로 위치 권한 필요)
- `ACCESS_FINE_LOCATION`
- API 30 이하: `BLUETOOTH`, `BLUETOOTH_ADMIN`, `ACCESS_FINE_LOCATION`

## 수신 특성 메모 (문서화된 제약)

- Android는 3개 광고 채널(37/38/39)을 순차 청취하지만 **수신 채널 번호를 API로 노출하지
  않는다** → 채널 필드는 null로 기록된다. P1의 3채널 차폐 감지는 채널을 노출하는
  수신기(nRF 등, 트랙3 실측 장비)나 Unity 시뮬 데이터에서 검증하고, 폰에서는
  잔차 기반 보정(코어 기본값)을 사용한다.
- 스캔 주기·배치는 제조사별 스로틀링 존재(5회/30초 제한 등) → `SCAN_MODE_LOW_LATENCY` +
  포그라운드 서비스 권장.

## 출력 포맷 (아키텍처.md와 동일 — 절대 변경 금지)

CSV: `timestamp,beacon_id,rssi,channel,x_true,y_true,noise_flag` (실측은 뒤 3개 공란)
