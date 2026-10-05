"""Hermes Desk Buddy Gateway — Main Server

FastAPI + WebSocket server. Bridge between J2 and Hermes/OmniRoute.
"""

import asyncio
import json
import time
import logging
import sys
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import (
    AUTH_TOKEN,
    GATEWAY_HOST,
    GATEWAY_PORT,
    HEARTBEAT_INTERVAL,
    HEARTBEAT_TIMEOUT,
)
from health import HealthMonitor
from pc_control import shutdown_pc, restart_pc, sleep_pc, cancel_shutdown, send_wol

# ── Logging ──────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("../logs/gateway.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("desk_buddy")


# ── Connected clients ────────────────────────────────────────────────

class DeskBuddyClient:
    """Represents one connected J2."""

    def __init__(self, ws: WebSocket, device_name: str = "unknown"):
        self.ws = ws
        self.device_name = device_name
        self.connected_at = time.time()
        self.last_pong = time.time()
        self.battery: Optional[int] = None
        self.wifi_rssi: Optional[int] = None
        self.app_version: Optional[str] = None
        self.current_state: str = "connected"

    def info(self) -> dict:
        return {
            "device_name": self.device_name,
            "connected": True,
            "connected_at": self.connected_at,
            "battery": self.battery,
            "wifi_rssi": self.wifi_rssi,
            "app_version": self.app_version,
            "current_state": self.current_state,
            "uptime_s": round(time.time() - self.connected_at),
        }


clients: dict[int, DeskBuddyClient] = {}


async def broadcast(event: dict):
    """Send an event to all connected J2 clients."""
    msg = json.dumps(event)
    dead = []
    for cid, client in clients.items():
        try:
            await client.ws.send_text(msg)
        except Exception:
            dead.append(cid)
    for cid in dead:
        clients.pop(cid, None)


# ── Health monitor ───────────────────────────────────────────────────

health_monitor = HealthMonitor(broadcast_fn=broadcast)


# ── App lifecycle ────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    await health_monitor.start()
    asyncio.create_task(_heartbeat_loop())
    asyncio.create_task(_spotify_poll_loop())
    logger.info("Desk Buddy Gateway started on %s:%d", GATEWAY_HOST, GATEWAY_PORT)
    logger.info("Auth token: %s", AUTH_TOKEN)
    yield
    await health_monitor.stop()
    logger.info("Desk Buddy Gateway stopped")


app = FastAPI(title="Hermes Desk Buddy Gateway", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Auth ─────────────────────────────────────────────────────────────

def verify_token(request: Request):
    """Check token from query param or Authorization header."""
    token = request.query_params.get("token")
    if not token:
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")
    if token != AUTH_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid token")
    return True


# ── Heartbeat loop ───────────────────────────────────────────────────

async def _heartbeat_loop():
    """Send pings and prune dead connections."""
    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL)
        now = time.time()
        dead = []
        for cid, client in list(clients.items()):
            try:
                await client.ws.send_text(json.dumps({"type": "ping", "ts": now}))
            except Exception:
                dead.append(cid)
                continue
            # Prune if no pong received in HEARTBEAT_TIMEOUT
            if now - client.last_pong > HEARTBEAT_TIMEOUT:
                dead.append(cid)
                logger.warning("Client %s timed out (no pong for %ds)",
                               client.device_name, int(now - client.last_pong))

        for cid in dead:
            c = clients.pop(cid, None)
            if c:
                logger.info("Client disconnected: %s", c.device_name)
                try:
                    await c.ws.close()
                except Exception:
                    pass


# ── REST endpoints ───────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "desk-buddy-gateway", "ts": time.time()}


@app.get("/system/status")
async def system_status(auth: bool = Depends(verify_token)):
    return {
        "services": health_monitor.health.to_dict(),
        "overall": health_monitor.health.overall_state(),
        "pc": health_monitor.get_pc_info(),
        "desk_buddy": {
            "connected_clients": len(clients),
            "clients": {cid: c.info() for cid, c in clients.items()},
        },
        "ts": time.time(),
    }


class PCActionRequest(BaseModel):
    confirm: bool = False
    delay: int = 10


@app.post("/pc/shutdown")
async def api_shutdown(req: PCActionRequest, auth: bool = Depends(verify_token)):
    if not req.confirm:
        return {"ok": False, "message": "Set confirm=true to proceed"}
    result = await shutdown_pc(req.delay)
    if result["ok"]:
        await broadcast({"type": "pc_action", "action": "shutdown", "delay": req.delay})
    return result


@app.post("/pc/restart")
async def api_restart(req: PCActionRequest, auth: bool = Depends(verify_token)):
    if not req.confirm:
        return {"ok": False, "message": "Set confirm=true to proceed"}
    result = await restart_pc(req.delay)
    if result["ok"]:
        await broadcast({"type": "pc_action", "action": "restart", "delay": req.delay})
    return result


@app.post("/pc/sleep")
async def api_sleep(req: PCActionRequest, auth: bool = Depends(verify_token)):
    if not req.confirm:
        return {"ok": False, "message": "Set confirm=true to proceed"}
    result = await sleep_pc()
    if result["ok"]:
        await broadcast({"type": "pc_action", "action": "sleep"})
    return result


@app.post("/pc/cancel-shutdown")
async def api_cancel_shutdown(auth: bool = Depends(verify_token)):
    return await cancel_shutdown()


@app.post("/pc/wake")
async def api_wake(auth: bool = Depends(verify_token)):
    result = send_wol()
    if result["ok"]:
        await broadcast({"type": "pc_action", "action": "wake"})
    return result


from scraper import get_upes_data
@app.get("/upes/data")
async def get_data(auth: bool = Depends(verify_token)):
    return {"data": "placeholder"}


@app.get("/omniroute/health")
async def omniroute_health(auth: bool = Depends(verify_token)):
    h = health_monitor.health.omniroute
    return {"state": h.state.value, "message": h.message, "last_check": h.last_check}


# ── WebSocket ────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, token: str = Query("")):
    if token != AUTH_TOKEN:
        await ws.close(code=4001, reason="Unauthorized")
        return

    await ws.accept()
    cid = id(ws)
    client = DeskBuddyClient(ws)
    clients[cid] = client
    logger.info("New client connected: id=%d", cid)

    # Send initial state sync
    await ws.send_text(json.dumps({
        "type": "state_sync",
        "services": health_monitor.health.to_dict(),
        "overall": health_monitor.health.overall_state(),
        "pc": health_monitor.get_pc_info(),
        "ts": time.time(),
    }))

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type", "")

            if msg_type == "pong" or msg_type == "ping":
                client.last_pong = time.time()
                if msg_type == "ping":
                    await ws.send_text(json.dumps({"type": "pong", "ts": time.time()}))

            elif msg_type == "device_info":
                client.device_name = msg.get("device_name", "unknown")
                client.battery = msg.get("battery")
                client.wifi_rssi = msg.get("wifi_rssi")
                client.app_version = msg.get("app_version")
                logger.info("Device info: %s battery=%s%% wifi=%sdBm v=%s",
                            client.device_name, client.battery,
                            client.wifi_rssi, client.app_version)

            elif msg_type == "state_update":
                client.current_state = msg.get("state", "unknown")

            elif msg_type == "command":
                # Handle commands from J2
                cmd = msg.get("command", "")
                await _handle_j2_command(ws, cmd, msg)

            elif msg_type == "request_sync":
                await ws.send_text(json.dumps({
                    "type": "state_sync",
                    "services": health_monitor.health.to_dict(),
                    "overall": health_monitor.health.overall_state(),
                    "pc": health_monitor.get_pc_info(),
                    "ts": time.time(),
                }))

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("WebSocket error for client %d", cid)
    finally:
        clients.pop(cid, None)
        logger.info("Client disconnected: id=%d name=%s", cid, client.device_name)


async def _handle_j2_command(ws: WebSocket, cmd: str, msg: dict):
    """Process commands sent from J2 over WebSocket."""
    result = {"type": "command_result", "command": cmd}

    if cmd == "wake_pc":
        r = send_wol()
        result.update(r)
    elif cmd == "shutdown_pc":
        r = await shutdown_pc(msg.get("delay", 10))
        result.update(r)
    elif cmd == "restart_pc":
        r = await restart_pc(msg.get("delay", 10))
        result.update(r)
    elif cmd == "sleep_pc":
        r = await sleep_pc()
        result.update(r)
    elif cmd == "cancel_shutdown":
        r = await cancel_shutdown()
        result.update(r)
    elif cmd == "get_status":
        result.update({
            "ok": True,
            "services": health_monitor.health.to_dict(),
            "overall": health_monitor.health.overall_state(),
            "pc": health_monitor.get_pc_info(),
        })
    elif cmd == "diagnostics":
        result.update({
            "ok": True,
            "services": health_monitor.health.to_dict(),
            "pc": health_monitor.get_pc_info(),
        })
    elif cmd in ("spotify_play_pause", "spotify_next", "spotify_prev"):
        r = await _spotify_control(cmd)
        result.update(r)
    elif cmd == "get_spotify_state":
        state = await _get_spotify_state()
        if state:
            await ws.send_text(json.dumps({"type": "spotify_state", **state}))
        result.update({"ok": True})
    elif cmd == "spotify_volume":
        vol = float(msg.get("volume", 0.7))  # 0.0 – 1.0
        try:
            from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume
            sessions = AudioUtilities.GetAllSessions()
            for session in sessions:
                if session.Process and "spotify" in session.Process.name().lower():
                    volume = session._ctl.QueryInterface(ISimpleAudioVolume)
                    volume.SetMasterVolume(max(0.0, min(1.0, vol)), None)
                    result.update({"ok": True, "volume": vol})
                    break
            else:
                result.update({"ok": False, "message": "Spotify session not found"})
        except Exception as e:
            result.update({"ok": False, "message": str(e)})
    elif cmd == "spotify_launch":
        try:
            import subprocess, os
            sp_path = r"C:\Users\Lenovo\AppData\Roaming\Spotify\Spotify.exe"
            if os.path.exists(sp_path):
                subprocess.Popen([sp_path])
                result.update({"ok": True, "message": "Spotify launching"})
            else:
                result.update({"ok": False, "message": "Spotify not found"})
        except Exception as e:
            result.update({"ok": False, "message": str(e)})
    elif cmd == "launch_app":
        result.update({"ok": True, "message": f"launch {msg.get('app')} not yet wired"})
    else:
        result.update({"ok": False, "message": f"Unknown command: {cmd}"})

    await ws.send_text(json.dumps(result))


# ── Spotify control (Windows media keys via ctypes) ───────────────────

async def _spotify_control(cmd: str) -> dict:
    try:
        import ctypes
        VK_MAP = {
            "spotify_play_pause": 0xB3,
            "spotify_next":       0xB0,
            "spotify_prev":       0xB1,
        }
        vk = VK_MAP.get(cmd)
        if vk:
            ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
            ctypes.windll.user32.keybd_event(vk, 0, 2, 0)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "message": str(e)}


# ── Spotify state poller ──────────────────────────────────────────────

_spotify_cache: dict = {}  # last known good track state

async def _spotify_poll_loop():
    """Poll Spotify state every 1s and broadcast."""
    global _spotify_cache
    _last_broadcast: dict = {}
    while True:
        await asyncio.sleep(1)
        if not clients:
            continue
        try:
            state = await _get_spotify_state()
            if state:
                await broadcast({"type": "spotify_state", **state})
        except Exception:
            pass


async def _get_spotify_state() -> dict:
    """Read Spotify state from process window title + iTunes art cache."""
    global _spotify_cache
    import subprocess

    # Window title is non-empty only when Spotify UI is alive (or playing a track)
    ps_title = "Get-Process Spotify -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -ne '' } | Select-Object -ExpandProperty MainWindowTitle -First 1"
    r_title = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_title],
            capture_output=True, text=True, timeout=3
        )
    )
    title = r_title.stdout.strip()
    
    # If no window has a title, Spotify UI is closed (only headless/background helpers exist)
    if not title:
        _spotify_cache = {}
        return {"playing": False, "is_playing": False, "spotify_open": False}

    is_playing = bool(title and title.lower() not in ("spotify", "spotify premium", "spotify free", ""))

    if not is_playing:
        # Spotify open but paused — return cached track with is_playing=False
        if _spotify_cache and _spotify_cache.get("track"):
            return {**_spotify_cache, "is_playing": False, "playing": True, "spotify_open": True}
        # If no track cached and nothing playing, it is closed or idle
        return {"playing": False, "is_playing": False, "spotify_open": False}

    # Parse artist/track
    if " - " in title:
        artist, track = title.split(" - ", 1)
    else:
        artist, track = "", title
    artist = artist.strip()
    track = track.strip()

    track_key = f"{artist}||{track}"
    same_track = (_spotify_cache.get("track") == track and _spotify_cache.get("artist") == artist)

    # Reuse cached art if same track; else broadcast immediately with no art then fetch in background
    art_url = _spotify_cache.get("art") if same_track else None

    state = {
        "playing": True, "is_playing": True, "spotify_open": True,
        "track": track, "artist": artist,
        "art": art_url, "progress": 0, "duration": 0,
    }
    _spotify_cache = state

    # If track changed, kick off art fetch in background — broadcasts update when done
    if not same_track:
        asyncio.ensure_future(_fetch_art_and_broadcast(artist, track))

    return state


async def _fetch_art_and_broadcast(artist: str, track: str):
    """Fetch iTunes art in background, update cache and broadcast immediately when done."""
    global _spotify_cache
    try:
        import urllib.request, urllib.parse, json as _json
        url = "https://itunes.apple.com/search?" + urllib.parse.urlencode(
            {"term": f"{artist} {track}", "media": "music", "limit": 1}
        )
        resp = await asyncio.get_event_loop().run_in_executor(
            None, lambda: urllib.request.urlopen(url, timeout=5)
        )
        data = _json.loads(resp.read())
        results = data.get("results", [])
        art_url = None
        if results:
            raw = results[0].get("artworkUrl100", "")
            art_url = raw.replace("100x100bb", "300x300bb") if raw else None
        if art_url and _spotify_cache.get("track") == track and _spotify_cache.get("artist") == artist:
            _spotify_cache["art"] = art_url
            # Broadcast the art update immediately to all clients
            await broadcast({"type": "spotify_state", **_spotify_cache})
    except Exception:
        pass


# ── /push endpoint — Hermes calls this to show a widget on J2 ─────────

class PushPayload(BaseModel):
    widget: str          # "table" | "text" | "image" | "spotify_state"
    title: str = ""
    data: list = []
    content: str = ""
    url: str = ""


@app.post("/push")
async def push_widget(payload: PushPayload, auth: bool = Depends(verify_token)):
    """Push any widget to the J2 display instantly."""
    event = {"type": "widget", "widget": payload.widget, "title": payload.title,
             "data": payload.data, "content": payload.content, "url": payload.url}
    await broadcast(event)
    return {"ok": True, "pushed_to": len(clients)}


import os
os.makedirs("static", exist_ok=True)
app.mount("/", StaticFiles(directory="static", html=True), name="static")

# ── Entry point ──────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "server:app",
        host=GATEWAY_HOST,
        port=GATEWAY_PORT,
        log_level="info",
        access_log=False,
    )
