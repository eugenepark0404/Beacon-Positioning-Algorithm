import CoreLocation

/// iBeacon RSSI 수신 — iOS에서 iBeacon은 CoreLocation 레인징으로만 접근 가능
/// (CoreBluetooth는 iBeacon 제조사 데이터를 노출하지 않음 — ios/README.md §1).
/// 샘플링 ~1 Hz 고정 (README §2).
final class IBeaconRanger: NSObject, CLLocationManagerDelegate {

    private let manager = CLLocationManager()
    private var constraints: [CLBeaconIdentityConstraint] = []
    var onSample: ((RssiSample) -> Void)?

    func start(uuids: [UUID]) {
        manager.delegate = self
        manager.requestWhenInUseAuthorization()
        constraints = uuids.map { CLBeaconIdentityConstraint(uuid: $0) }
        for c in constraints { manager.startRangingBeacons(satisfying: c) }
    }

    func stop() {
        for c in constraints { manager.stopRangingBeacons(satisfying: c) }
        constraints = []
    }

    func locationManager(_ manager: CLLocationManager,
                         didRange beacons: [CLBeacon],
                         satisfying constraint: CLBeaconIdentityConstraint) {
        let now = Date().timeIntervalSince1970
        for b in beacons where b.rssi != 0 {   // rssi==0 은 무효 샘플
            onSample?(RssiSample(
                timestamp: now,
                beaconId: "\(b.uuid.uuidString.lowercased())/\(b.major)/\(b.minor)",
                rssi: b.rssi,
                protocolName: "ibeacon",
                measuredPower1m: nil   // CLBeacon은 광고 txPower를 노출하지 않음 → config로 주입
            ))
        }
    }
}
