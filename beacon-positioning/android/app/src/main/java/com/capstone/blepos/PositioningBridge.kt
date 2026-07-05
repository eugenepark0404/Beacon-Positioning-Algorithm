package com.capstone.blepos

/**
 * 온디바이스 측위 연동 인터페이스 (사용자 결정: 온디바이스/로컬 기본).
 *
 * 현재 레퍼런스 구현은 Python 코어(ble_positioning/)이며, 검증 완료된 알고리즘을
 * 이 인터페이스 뒤로 Kotlin 이식한다. 이식 대상·순서:
 *   1) SlidingWindowFilter(median, n=10)  # ref: P3 §V-A
 *   2) LogDistanceModel                    # ref: P1 Eq.(1)
 *   3) trilaterate_nls + WCL fallback      # ref: P1 §2 / P3 §III-D
 *   4) 잔차 기반 차폐 보정                  # ref: 유도서 §3.4
 * 트랙2 융합(PF)은 FusionEngine 규격(fusion/interfaces.py)을 따라 별도 모듈로.
 */
interface PositioningBridge {
    data class Position(val x: Double, val y: Double, val nBeacons: Int, val method: String)

    /** 비콘 좌표 맵 주입 (config/beacon_map.json 과 동일 내용) */
    fun setBeaconMap(map: Map<String, Pair<Double, Double>>)

    /** 스캔 샘플 공급 → 최신 위치 추정 (null = 비콘 부족) */
    fun onSample(sample: BeaconScanner.RssiSample): Position?
}
