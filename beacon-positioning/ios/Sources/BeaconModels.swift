import Foundation

/// 코어 알고리즘 공용 샘플 모델 — Android BeaconScanner.RssiSample 과 동일 의미.
struct RssiSample: Codable {
    let timestamp: Double        // epoch [s]
    let beaconId: String         // iBeacon: "uuid/major/minor", Eddystone: "ns/instance"
    let rssi: Int                // [dBm]
    let protocolName: String     // "ibeacon" | "eddystone-uid"
    let measuredPower1m: Int?    // A = RSSI@1m (iBeacon 광고 txPower; 코어 a_dbm 후보)

    enum CodingKeys: String, CodingKey {
        case timestamp = "t", beaconId = "beacon_id", rssi
        case protocolName = "protocol", measuredPower1m = "measured_power_1m"
    }
}
