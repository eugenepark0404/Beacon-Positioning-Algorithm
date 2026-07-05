import CoreBluetooth

/// Eddystone-UID 스캔 — 서비스 데이터 0xFEAA는 CoreBluetooth에 노출된다 (README §3).
final class EddystoneScanner: NSObject, CBCentralManagerDelegate {

    static let eddystoneUUID = CBUUID(string: "FEAA")
    /// Eddystone txPower는 0m 기준 → 1m 환산 관례 -41dB. PLACEHOLDER (트랙3 실측 교체)
    static let tx0mTo1mDb = -41

    private var central: CBCentralManager!
    var onSample: ((RssiSample) -> Void)?

    func start() {
        central = CBCentralManager(delegate: self, queue: nil)
    }

    func stop() {
        central?.stopScan()
    }

    func centralManagerDidUpdateState(_ central: CBCentralManager) {
        guard central.state == .poweredOn else { return }
        // 백그라운드에서는 서비스 UUID 필터가 필수 (README §3)
        central.scanForPeripherals(withServices: [Self.eddystoneUUID],
                                   options: [CBCentralManagerScanOptionAllowDuplicatesKey: true])
    }

    func centralManager(_ central: CBCentralManager,
                        didDiscover peripheral: CBPeripheral,
                        advertisementData: [String: Any],
                        rssi RSSI: NSNumber) {
        guard let serviceData = advertisementData[CBAdvertisementDataServiceDataKey]
                as? [CBUUID: Data],
              let data = serviceData[Self.eddystoneUUID],
              data.count >= 18, data[0] == 0x00 else { return }  // 0x00 = UID 프레임

        let tx0m = Int(Int8(bitPattern: data[1]))
        let ns = data[2..<12].map { String(format: "%02x", $0) }.joined()
        let inst = data[12..<18].map { String(format: "%02x", $0) }.joined()

        onSample?(RssiSample(
            timestamp: Date().timeIntervalSince1970,
            beaconId: "\(ns)/\(inst)",
            rssi: RSSI.intValue,
            protocolName: "eddystone-uid",
            measuredPower1m: tx0m + Self.tx0mTo1mDb
        ))
    }
}
