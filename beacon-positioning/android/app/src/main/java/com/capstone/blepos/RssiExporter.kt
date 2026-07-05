package com.capstone.blepos

import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/**
 * 코어 알고리즘 공용 포맷 내보내기 — iOS 와 완전히 동일한 스키마 (변경 금지).
 * CSV 헤더: timestamp,beacon_id,rssi,channel,x_true,y_true,noise_flag
 * JSON: {"meta": {...}, "samples": [{"t","beacon_id","rssi","channel"}, ...]}
 */
class RssiExporter {

    private val samples = mutableListOf<BeaconScanner.RssiSample>()

    fun add(s: BeaconScanner.RssiSample) = synchronized(samples) { samples.add(s) }

    fun toCsv(file: File) {
        synchronized(samples) {
            file.printWriter().use { w ->
                w.println("timestamp,beacon_id,rssi,channel,x_true,y_true,noise_flag")
                samples.forEach { s ->
                    w.println("${s.timestamp},${s.beaconId},${s.rssi},,,,")
                }
            }
        }
    }

    fun toJson(file: File, meta: Map<String, String> = emptyMap()) {
        synchronized(samples) {
            val arr = JSONArray()
            samples.forEach { s ->
                arr.put(JSONObject().apply {
                    put("t", s.timestamp)
                    put("beacon_id", s.beaconId)
                    put("rssi", s.rssi)
                    put("channel", JSONObject.NULL)
                })
            }
            val root = JSONObject().apply {
                put("meta", JSONObject(meta + mapOf("source" to "android", "format" to "track4-unity-v1")))
                put("samples", arr)
            }
            file.writeText(root.toString(1))
        }
    }

    fun clear() = synchronized(samples) { samples.clear() }
    val size: Int get() = synchronized(samples) { samples.size }
}
