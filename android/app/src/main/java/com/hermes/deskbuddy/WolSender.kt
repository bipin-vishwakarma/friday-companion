package com.hermes.deskbuddy

import android.util.Log
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import kotlin.concurrent.thread

/**
 * Sends a Wake-on-LAN magic packet directly from the J2.
 * Works even when the PC gateway is down — pure UDP broadcast.
 */
object WolSender {

    private const val TAG = "WolSender"
    private const val WOL_PORT = 9

    fun send(macAddress: String, broadcastIp: String, onResult: (Boolean, String) -> Unit) {
        thread(name = "wol-sender") {
            try {
                val packet = buildMagicPacket(macAddress)
                val address = InetAddress.getByName(broadcastIp)
                DatagramSocket().use { socket ->
                    socket.broadcast = true
                    val dp = DatagramPacket(packet, packet.size, address, WOL_PORT)
                    socket.send(dp)
                    // Send 3 times for reliability
                    socket.send(dp)
                    socket.send(dp)
                }
                Log.i(TAG, "WoL sent to $macAddress via $broadcastIp")
                onResult(true, "Wake-on-LAN sent to $macAddress")
            } catch (e: Exception) {
                Log.e(TAG, "WoL failed: ${e.message}")
                onResult(false, e.message ?: "Unknown error")
            }
        }
    }

    private fun buildMagicPacket(mac: String): ByteArray {
        // Normalize MAC: accept "AA:BB:CC:DD:EE:FF" or "AA-BB-CC-DD-EE-FF"
        val hex = mac.replace(":", "").replace("-", "").uppercase()
        require(hex.length == 12) { "Invalid MAC: $mac" }

        val macBytes = ByteArray(6) { hex.substring(it * 2, it * 2 + 2).toInt(16).toByte() }

        // Magic packet: 6×0xFF + 16× MAC address = 102 bytes
        val packet = ByteArray(6 + 16 * 6)
        for (i in 0..5) packet[i] = 0xFF.toByte()
        for (i in 0 until 16) {
            System.arraycopy(macBytes, 0, packet, 6 + i * 6, 6)
        }
        return packet
    }
}
