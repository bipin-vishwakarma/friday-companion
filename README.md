# 🎙️ Friday Companion (Formerly Desk Buddy)

Friday is an autonomous desktop companion interface running on a low-end Android display (Samsung Galaxy J2 Core) backed by a local Windows Python FastAPI Gateway.

![GitHub repo size](https://img.shields.io/github/repo-size/bipin-vishwakarma/friday-companion)
![License](https://img.shields.io/badge/license-MIT-blue)

---

## 🏗️ Architecture & Philosophy

1. **Thin-Client Android Target**:
   - The Samsung J2 Core (SM-J260GU, 1GB RAM, Adreno 308) runs a native Android APK serving as an edge-to-edge, screen-pinned hardware-accelerated WebView.
   - **Zero Rebuild Deployments**: Any visual layout, component updates, or UI additions are delivered via HTML5/WebGL served directly from the local gateway over Wi-Fi (`http://<PC-IP>:8765/`).
2. **Python Gateway (`gateway/server.py`)**:
   - FastAPI + WebSocket hub running locally on Windows.
   - Polls system vitals (CPU/RAM/Disk/Ping/Processes via `psutil`).
   - Hooks into Spotify desktop client via Win32 API + `pycaw` audio endpoints.
   - Triggers native Windows Sleep (`SetSuspendState`), Restart, Shutdown, and Wake-on-LAN.
3. **Voice Engine**:
   - Configured with a natural, crisp male persona (Friday).

---

## 🚀 Complete Setup & Deployment Guide

### Prerequisites
- Python 3.10+ installed on host PC.
- Android device connected via Wi-Fi or USB ADB.
- NSSM (Non-Sucking Service Manager) for persistent daemon service.

### 1. Gateway Installation
```bash
cd gateway
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Auto-Start Service (Persistent Windows Daemon)
Run the automated installation script inside an **Administrator PowerShell** session:
```powershell
.\install-service.ps1
```
This registers `DeskBuddyGateway` as a resilient background Windows Service that auto-starts on PC boot and self-heals after crashes.

### 3. Deploying to the J2 Core
Ensure your phone is in USB Debugging mode:
```bash
# Push and install the initial WebView thin-client APK
adb install -r android/app/build/outputs/apk/debug/app-debug.apk

# Launch the interface
adb shell am start -n com.hermes.deskbuddy/.MainActivity
```

---

## 🎵 Features
- **Fluid Orb HUD**: Custom WebGL interactive fluid sphere running at 30fps capped for low-power mobile GPUs.
- **Spotify Remote**:
  - Auto-detection of open vs. closed states.
  - Asynchronous background album art extraction (iTunes CDN caching).
  - True app-level volume slider powered by `pycaw`.
  - Media key controls (Play, Pause, Skip, Previous).
- **System Telemetry**: Real-time CPU, RAM, and Disk metrics.
- **Power Controls**: Confirmation-gated Sleep, Restart, and Shutdown commands.
