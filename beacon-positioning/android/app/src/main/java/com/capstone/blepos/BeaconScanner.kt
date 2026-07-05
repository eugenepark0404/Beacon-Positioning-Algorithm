package com.capstone.blepos

import android.annotation.SuppressLint
import android.bluetooth.BluetoothManager
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.content.Context

/**
 * BLE 스캔 → RSSI 샘플 스트림.
 *
 * 코어 입력 포맷과 1:1 대응하는 RssiSample 을 콜백으로 전달한다.
 * channel 은 Android API가 수신 채널을 노출하지 않으므로 null (android/README.md 참조).
 */
class BeaconScanner(context: Context) {

    data class RssiSample(
        val timestamp: Double,     // epoch [s]
        val beaconId: String,
        val rssi: Int,             // [dBm]
        val protocol: String,
        val measuredPower1m: Int?, // 광고에 실린 A 값 (캘리브레이션 힌트)
    )

    private val adapter = (context.getSystemService(Context.BLUETOOTH_SERVICE)
            as BluetoothManager).adapter
    private var listener: ((RssiSample) -> Unit)? = null

    private val callback = object : ScanCallback() {
        override fun onScanResult(callbackType: Int, result: ScanResult) {
            val beacon = BeaconParser.parse(result) ?: return
            listener?.invoke(
                RssiSample(
                    timestamp = System.currentTimeMillis() / 1000.0,
                    beaconId = beacon.beaconId,
                    rssi = result.rssi,
                    protocol = beacon.protocol,
                    measuredPower1m = beacon.measuredPower1m,
                )
            )
        }
    }

    /** 호출 전 BLUETOOTH_SCAN + ACCESS_FINE_LOCATION 런타임 권한 필요 (MainActivity 참조). */
    @SuppressLint("MissingPermission")
    fun start(onSample: (RssiSample) -> Unit) {
        listener = onSample
        val settings = ScanSettings.Builder()
            .setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY)  // 측위용 고빈도 샘플링
            .build()
        adapter.bluetoothLeScanner.startScan(null, settings, callback)
    }

    @SuppressLint("MissingPermission")
    fun stop() {
        adapter.bluetoothLeScanner?.stopScan(callback)
        listener = null
    }
}
