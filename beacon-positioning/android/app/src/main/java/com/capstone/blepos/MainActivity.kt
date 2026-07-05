package com.capstone.blepos

import android.Manifest
import android.os.Build
import android.os.Bundle
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import androidx.activity.ComponentActivity
import androidx.activity.result.contract.ActivityResultContracts
import java.io.File

/** 최소 동작 데모: 권한 → 스캔 → 카운트 표시 → JSON/CSV 내보내기. */
class MainActivity : ComponentActivity() {

    private lateinit var scanner: BeaconScanner
    private val exporter = RssiExporter()
    private lateinit var status: TextView

    private val permissionLauncher =
        registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { grants ->
            if (grants.values.all { it }) startScan()
            else status.text = "권한 거부됨 — 스캔 불가"
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        scanner = BeaconScanner(this)
        status = TextView(this).apply { text = "대기" }

        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            addView(status)
            addView(Button(context).apply {
                text = "스캔 시작"
                setOnClickListener { requestPermissionsAndScan() }
            })
            addView(Button(context).apply {
                text = "스캔 정지 + 내보내기"
                setOnClickListener {
                    scanner.stop()
                    val dir = getExternalFilesDir(null) ?: filesDir
                    exporter.toJson(File(dir, "rssi_log.json"))
                    exporter.toCsv(File(dir, "rssi_log.csv"))
                    status.text = "저장 완료: ${exporter.size}건 → $dir"
                }
            })
        }
        setContentView(layout)
    }

    private fun requestPermissionsAndScan() {
        val perms = if (Build.VERSION.SDK_INT >= 31)
            arrayOf(Manifest.permission.BLUETOOTH_SCAN, Manifest.permission.ACCESS_FINE_LOCATION)
        else
            arrayOf(Manifest.permission.ACCESS_FINE_LOCATION)
        permissionLauncher.launch(perms)
    }

    private fun startScan() {
        scanner.start { sample ->
            exporter.add(sample)
            runOnUiThread { status.text = "수신 ${exporter.size}건 (마지막: ${sample.beaconId} ${sample.rssi}dBm)" }
        }
        status.text = "스캔 중..."
    }

    override fun onDestroy() {
        scanner.stop()
        super.onDestroy()
    }
}
