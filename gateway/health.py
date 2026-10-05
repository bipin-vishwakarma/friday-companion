"""Hermes Desk Buddy Gateway — Health Monitor

Polls the service chain and broadcasts state changes over WebSocket.
"""

import asyncio
import json
import time
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional

import httpx
import psutil

_GATEWAY_START = __import__('time').time()

from config import (
    GATEWAY_STATE_FILE,
    OMNIROUTE_URL,
    OMNIROUTE_HEALTH_ENDPOINT,
    HEALTH_CHECK_INTERVAL,
)

logger = logging.getLogger("desk_buddy.health")


class ServiceState(str, Enum):
    UNKNOWN = "unknown"
    STARTING = "starting"
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    OFFLINE = "offline"
    STOPPING = "stopping"


@dataclass
class ServiceStatus:
    name: str
    state: ServiceState = ServiceState.UNKNOWN
    message: str = ""
    last_check: float = 0.0
    last_healthy: float = 0.0
    consecutive_failures: int = 0


@dataclass
class SystemHealth:
    windows: ServiceStatus = field(default_factory=lambda: ServiceStatus("windows", ServiceState.HEALTHY))
    network: ServiceStatus = field(default_factory=lambda: ServiceStatus("network"))
    gateway: ServiceStatus = field(default_factory=lambda: ServiceStatus("gateway", ServiceState.HEALTHY))
    omniroute: ServiceStatus = field(default_factory=lambda: ServiceStatus("omniroute"))
    hermes: ServiceStatus = field(default_factory=lambda: ServiceStatus("hermes"))
    telegram: ServiceStatus = field(default_factory=lambda: ServiceStatus("telegram"))
    tts: ServiceStatus = field(default_factory=lambda: ServiceStatus("tts"))

    def to_dict(self) -> dict:
        result = {}
        for svc_name in ["windows", "network", "gateway", "omniroute", "hermes", "telegram", "tts"]:
            svc: ServiceStatus = getattr(self, svc_name)
            result[svc_name] = {
                "state": svc.state.value,
                "message": svc.message,
                "last_check": svc.last_check,
            }
        return result

    def overall_state(self) -> str:
        """Return the overall system readiness."""
        critical = [self.omniroute, self.hermes]
        if all(s.state == ServiceState.HEALTHY for s in critical):
            return "online"
        if any(s.state == ServiceState.OFFLINE for s in critical):
            return "degraded"
        if all(s.state == ServiceState.OFFLINE for s in critical):
            return "offline"
        return "starting"


class HealthMonitor:
    """Continuously monitors the Hermes service chain."""

    def __init__(self, broadcast_fn):
        self.health = SystemHealth()
        self._broadcast = broadcast_fn
        self._running = False
        self._http = httpx.AsyncClient(timeout=5.0)
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Health monitor started (interval=%ds)", HEALTH_CHECK_INTERVAL)

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self._http.aclose()

    async def _loop(self):
        while self._running:
            try:
                await self._check_all()
            except Exception:
                logger.exception("Health check cycle failed")
            await asyncio.sleep(HEALTH_CHECK_INTERVAL)

    async def _check_all(self):
        now = time.time()

        # Network — can we reach the gateway's own loopback?
        await self._check_network(now)

        # OmniRoute
        await self._check_omniroute(now)

        # Hermes — read gateway_state.json
        await self._check_hermes(now)

        # Telegram — from hermes gateway state
        await self._check_telegram(now)

        # Always broadcast a full state_sync with live PC vitals every cycle
        await self._broadcast({
            "type": "state_sync",
            "services": self.health.to_dict(),
            "overall": self.health.overall_state(),
            "pc": self.get_pc_info(),
            "ts": now,
        })

    async def _check_network(self, now: float):
        old = self.health.network.state
        try:
            # Simple test: can we make any TCP connection?
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection("8.8.8.8", 53), timeout=3
            )
            writer.close()
            await writer.wait_closed()
            self._update_service(self.health.network, ServiceState.HEALTHY, "", now)
        except Exception:
            self._update_service(self.health.network, ServiceState.OFFLINE, "No internet", now)

        if old != self.health.network.state:
            await self._emit_change("network", self.health.network)

    async def _check_omniroute(self, now: float):
        old = self.health.omniroute.state
        try:
            r = await self._http.get(f"{OMNIROUTE_URL}{OMNIROUTE_HEALTH_ENDPOINT}")
            if r.status_code == 200:
                self._update_service(self.health.omniroute, ServiceState.HEALTHY, "", now)
            else:
                self._update_service(
                    self.health.omniroute, ServiceState.UNHEALTHY,
                    f"HTTP {r.status_code}", now
                )
        except httpx.ConnectError:
            self._update_service(self.health.omniroute, ServiceState.OFFLINE, "Connection refused", now)
        except Exception as e:
            self._update_service(self.health.omniroute, ServiceState.UNHEALTHY, str(e), now)

        if old != self.health.omniroute.state:
            await self._emit_change("omniroute", self.health.omniroute)

    async def _check_hermes(self, now: float):
        old = self.health.hermes.state
        try:
            if GATEWAY_STATE_FILE.exists():
                logger.info(f"Health Monitor: Reading gateway state from {GATEWAY_STATE_FILE}")
                data = json.loads(GATEWAY_STATE_FILE.read_text())
                gw_state = data.get("gateway_state", "")
                if gw_state == "running":
                    self._update_service(self.health.hermes, ServiceState.HEALTHY, "", now)
                elif gw_state in ("starting", "restarting"):
                    self._update_service(self.health.hermes, ServiceState.STARTING, gw_state, now)
                else:
                    self._update_service(self.health.hermes, ServiceState.UNHEALTHY, gw_state, now)
            else:
                self._update_service(self.health.hermes, ServiceState.OFFLINE, "No gateway state file", now)
        except Exception as e:
            self._update_service(self.health.hermes, ServiceState.UNHEALTHY, str(e), now)

        if old != self.health.hermes.state:
            await self._emit_change("hermes", self.health.hermes)

    async def _check_telegram(self, now: float):
        old = self.health.telegram.state
        try:
            if GATEWAY_STATE_FILE.exists():
                logger.info(f"Health Monitor: Reading gateway state from {GATEWAY_STATE_FILE}")
                data = json.loads(GATEWAY_STATE_FILE.read_text())
                platforms = data.get("platforms", {})
                tg = platforms.get("telegram", {})
                tg_state = tg.get("state", "")
                if tg_state == "connected":
                    self._update_service(self.health.telegram, ServiceState.HEALTHY, "", now)
                elif tg_state in ("connecting", "reconnecting"):
                    self._update_service(self.health.telegram, ServiceState.STARTING, tg_state, now)
                else:
                    self._update_service(self.health.telegram, ServiceState.OFFLINE, tg_state, now)
            else:
                self._update_service(self.health.telegram, ServiceState.OFFLINE, "No state file", now)
        except Exception as e:
            self._update_service(self.health.telegram, ServiceState.UNHEALTHY, str(e), now)

        if old != self.health.telegram.state:
            await self._emit_change("telegram", self.health.telegram)

    def _update_service(self, svc: ServiceStatus, state: ServiceState, msg: str, now: float):
        svc.state = state
        svc.message = msg
        svc.last_check = now
        if state == ServiceState.HEALTHY:
            svc.last_healthy = now
            svc.consecutive_failures = 0
        else:
            svc.consecutive_failures += 1

    async def _emit_change(self, name: str, svc: ServiceStatus):
        event = {
            "type": "service_state",
            "service": name,
            "state": svc.state.value,
            "message": svc.message,
            "ts": svc.last_check,
        }
        logger.info("Service %s → %s %s", name, svc.state.value, svc.message)
        await self._broadcast(event)

    def get_pc_info(self) -> dict:
        """Get current PC system info."""
        try:
            cpu_pct = psutil.cpu_percent(interval=0)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage("C:\\")

            # Top CPU process — normalize by cpu_count
            top_proc = {"name": "—", "cpu": 0.0}
            try:
                cpu_count = psutil.cpu_count() or 1
                procs = [(p.info["name"], p.info["cpu_percent"] / cpu_count)
                         for p in psutil.process_iter(["name", "cpu_percent"])
                         if p.info["cpu_percent"] and p.info["name"]]
                if procs:
                    top = max(procs, key=lambda x: x[1])
                    top_proc = {"name": top[0][:20], "cpu": round(top[1], 1)}
            except Exception:
                pass

            # Local IP
            import socket
            local_ip = "—"
            try:
                local_ip = socket.gethostbyname(socket.gethostname())
            except Exception:
                pass

            # Gateway uptime
            uptime_s = round(time.time() - _GATEWAY_START)

            return {
                "cpu_percent": cpu_pct,
                "ram_total_gb": round(mem.total / (1024**3), 1),
                "ram_used_percent": mem.percent,
                "disk_total_gb": round(disk.total / (1024**3), 1),
                "disk_used_percent": round(disk.percent, 1),
                "boot_time": psutil.boot_time(),
                "uptime_hours": round((time.time() - psutil.boot_time()) / 3600, 1),
                "top_proc": top_proc,
                "local_ip": local_ip,
                "gateway_uptime_s": uptime_s,
            }
        except Exception as e:
            logger.error("Failed to get PC info: %s", e)
            return {"error": str(e)}
