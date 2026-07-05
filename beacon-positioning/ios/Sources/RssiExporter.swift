import Foundation

/// Android RssiExporter.kt 와 완전히 동일한 스키마 (변경 금지).
/// CSV: timestamp,beacon_id,rssi,channel,x_true,y_true,noise_flag
final class RssiExporter {

    private var samples: [RssiSample] = []
    private let lock = NSLock()

    func add(_ s: RssiSample) {
        lock.lock(); defer { lock.unlock() }
        samples.append(s)
    }

    var count: Int {
        lock.lock(); defer { lock.unlock() }
        return samples.count
    }

    func writeCsv(to url: URL) throws {
        lock.lock(); defer { lock.unlock() }
        var out = "timestamp,beacon_id,rssi,channel,x_true,y_true,noise_flag\n"
        for s in samples {
            out += "\(s.timestamp),\(s.beaconId),\(s.rssi),,,,\n"
        }
        try out.write(to: url, atomically: true, encoding: .utf8)
    }

    func writeJson(to url: URL, meta: [String: String] = [:]) throws {
        lock.lock(); defer { lock.unlock() }
        var metaAll = meta
        metaAll["source"] = "ios"
        metaAll["format"] = "track4-unity-v1"
        let payload: [String: Any] = [
            "meta": metaAll,
            "samples": samples.map { s -> [String: Any] in
                ["t": s.timestamp, "beacon_id": s.beaconId, "rssi": s.rssi,
                 "channel": NSNull()]
            },
        ]
        let data = try JSONSerialization.data(withJSONObject: payload,
                                              options: [.prettyPrinted])
        try data.write(to: url)
    }

    func clear() {
        lock.lock(); defer { lock.unlock() }
        samples.removeAll()
    }
}
