# iOS BLE 수신부 (트랙1 — 수신 파이프라인, Swift)

## iOS 플랫폼 제약 (중요 — 설계에 반영됨)

1. **iBeacon은 CoreBluetooth로 읽을 수 없다.** iOS는 iBeacon 광고(제조사 데이터
   0x004C/0x02/0x15)를 OS 레벨에서 가로채 CoreBluetooth 스캔 콜백에 노출하지 않는다.
   → iBeacon RSSI는 **CoreLocation의 CLBeacon 레인징**(`IBeaconRanger.swift`)으로 받는다.
2. **CLBeacon 레인징은 ~1 Hz 고정.** Android(수십 Hz)보다 샘플링이 성기다.
   → 코어의 scan_window_s(1s) 창에서 창당 1샘플 → 필터 윈도우가 곧 시간축(10s)이 됨을
   문서화. 밀집 환경 실측 시 고려.
3. **Eddystone은 CoreBluetooth로 읽을 수 있다** (서비스 데이터 0xFEAA는 노출됨) —
   `EddystoneScanner.swift`. 단, 백그라운드에서는 서비스 UUID 필터 필수 + 성능 저하.
4. **백그라운드 한계**: CLBeacon 레인징은 백그라운드에서 리전 진입 이벤트 직후 잠깐만
   동작. 연속 측위는 포그라운드 전제 (지하철 내비 UX는 포그라운드+음성이므로 수용 가능).
5. 수신 채널(37/38/39) 번호는 iOS도 노출하지 않는다 → channel=null.
   (P1 3채널 차폐 감지는 시뮬/전용 수신기 검증용, 폰은 잔차 보정 사용 — android/README 동일)

## 출력 포맷

Android와 완전히 동일 (RssiExporter.swift): CSV/JSON, 스키마 변경 금지.

## 파일

- `BeaconModels.swift` — 공용 샘플 모델
- `IBeaconRanger.swift` — CoreLocation iBeacon 레인징 (기본 경로)
- `EddystoneScanner.swift` — CoreBluetooth Eddystone-UID 스캔
- `RssiExporter.swift` — CSV/JSON 내보내기

Info.plist 필수 키: `NSLocationWhenInUseUsageDescription`, `NSBluetoothAlwaysUsageDescription`
