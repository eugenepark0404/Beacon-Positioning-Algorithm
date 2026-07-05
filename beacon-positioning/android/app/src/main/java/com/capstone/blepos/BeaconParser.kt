package com.capstone.blepos

import android.bluetooth.le.ScanResult

/**
 * 비콘 광고 파싱: iBeacon + Eddystone(UID/TLM) 둘 다 지원 (사용자 결정: 둘 다 구현).
 *
 * iBeacon 프레임 (제조사 데이터, company=0x004C):
 *   [0]=0x02(type) [1]=0x15(len) [2..17]=UUID [18..19]=major [20..21]=minor [22]=txPower(1m)
 * Eddystone (서비스 데이터, UUID 0xFEAA):
 *   frame 0x00(UID): [1]=txPower(0m 기준!) [2..11]=namespace [12..17]=instance
 *   frame 0x20(TLM): 전압/온도 등 텔레메트리 (RSSI 캘리브레이션 참고용)
 *
 * 주의: Eddystone txPower는 0m 기준, iBeacon measuredPower는 1m 기준.
 * 코어의 A(=RSSI@1m)로 쓸 때 Eddystone은 -41dB 보정 관례 적용 (트랙3 실측으로 확정).
 */
object BeaconParser {

    const val EDDYSTONE_TX_AT_0M_TO_1M_DB = -41  // 관례값 PLACEHOLDER (트랙3 실측 교체)

    data class Beacon(
        val beaconId: String,      // iBeacon: "uuid/major/minor", Eddystone: "ns/instance"
        val protocol: String,      // "ibeacon" | "eddystone-uid"
        val measuredPower1m: Int?, // A = RSSI@1m [dBm] (코어 path_loss.a_dbm 후보)
    )

    fun parse(result: ScanResult): Beacon? {
        val record = result.scanRecord ?: return null

        // --- iBeacon ---
        record.getManufacturerSpecificData(0x004C)?.let { m ->
            if (m.size >= 23 && m[0].toInt() == 0x02 && m[1].toInt() == 0x15) {
                val uuid = buildString {
                    for (i in 2 until 18) append("%02x".format(m[i]))
                }
                val major = ((m[18].toInt() and 0xFF) shl 8) or (m[19].toInt() and 0xFF)
                val minor = ((m[20].toInt() and 0xFF) shl 8) or (m[21].toInt() and 0xFF)
                val tx = m[22].toInt()  // signed byte = measured power @1m
                return Beacon("$uuid/$major/$minor", "ibeacon", tx)
            }
        }

        // --- Eddystone-UID ---
        val eddystoneUuid = android.os.ParcelUuid.fromString("0000FEAA-0000-1000-8000-00805F9B34FB")
        record.serviceData?.get(eddystoneUuid)?.let { d ->
            if (d.isNotEmpty() && d[0].toInt() == 0x00 && d.size >= 18) {
                val tx0m = d[1].toInt()
                val ns = (2 until 12).joinToString("") { "%02x".format(d[it]) }
                val inst = (12 until 18).joinToString("") { "%02x".format(d[it]) }
                return Beacon("$ns/$inst", "eddystone-uid", tx0m + EDDYSTONE_TX_AT_0M_TO_1M_DB)
            }
        }
        return null
    }
}
