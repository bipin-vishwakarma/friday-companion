"""Hermes Desk Buddy Gateway — PC Control

Shutdown, restart, sleep, WoL — all gated behind auth + confirmation.
"""

import asyncio
import subprocess
import logging
from typing import Optional

from wakeonlan import send_magic_packet

from config import PC_MAC_WIFI, PC_MAC_ETH, PC_BROADCAST

logger = logging.getLogger("desk_buddy.pc_control")


async def shutdown_pc(delay: int = 10) -> dict:
    """Graceful Windows shutdown."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "shutdown", "/s", "/t", str(delay),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            logger.info("PC shutdown initiated (delay=%ds)", delay)
            return {"ok": True, "message": f"Shutting down in {delay} seconds"}
        else:
            msg = stderr.decode().strip()
            logger.error("Shutdown failed: %s", msg)
            return {"ok": False, "message": msg}
    except Exception as e:
        logger.exception("Shutdown error")
        return {"ok": False, "message": str(e)}


async def restart_pc(delay: int = 10) -> dict:
    """Graceful Windows restart."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "shutdown", "/r", "/t", str(delay),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            logger.info("PC restart initiated (delay=%ds)", delay)
            return {"ok": True, "message": f"Restarting in {delay} seconds"}
        else:
            return {"ok": False, "message": stderr.decode().strip()}
    except Exception as e:
        return {"ok": False, "message": str(e)}


async def sleep_pc() -> dict:
    """Put PC to sleep."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "rundll32.exe", "powrprof.dll,SetSuspendState", "0", "1", "0",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        logger.info("PC sleep initiated")
        return {"ok": True, "message": "Going to sleep"}
    except Exception as e:
        return {"ok": False, "message": str(e)}


async def cancel_shutdown() -> dict:
    """Cancel a pending shutdown/restart."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "shutdown", "/a",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            return {"ok": True, "message": "Shutdown cancelled"}
        else:
            return {"ok": False, "message": stderr.decode().strip()}
    except Exception as e:
        return {"ok": False, "message": str(e)}


def send_wol() -> dict:
    """Send Wake-on-LAN magic packet to the PC (called from J2's perspective,
    but also available on the gateway for self-wake after sleep)."""
    try:
        # Try both MACs — Wi-Fi and Ethernet
        send_magic_packet(PC_MAC_WIFI, ip_address=PC_BROADCAST, port=9)
        send_magic_packet(PC_MAC_ETH, ip_address=PC_BROADCAST, port=9)
        logger.info("WoL packets sent to %s and %s", PC_MAC_WIFI, PC_MAC_ETH)
        return {"ok": True, "message": "Wake-on-LAN sent"}
    except Exception as e:
        logger.exception("WoL failed")
        return {"ok": False, "message": str(e)}
