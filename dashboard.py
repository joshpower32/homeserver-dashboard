#!/usr/bin/env python3
"""
Homeserver Dashboard — backend
joshuadanielca@homeserver
Access: http://192.168.1.12:5000
"""
from flask import Flask, jsonify, render_template
import psutil, os, json, glob, time
from collections import deque
from datetime import datetime

app = Flask(__name__)

# Paths
HUNT_DIR   = os.path.expanduser("~/hunting")
LOGS_DIR   = os.path.join(HUNT_DIR, "logs")
CONFIG_DIR = os.path.join(HUNT_DIR, "configs")

# Cron job definitions — adjust log filenames if yours differ
CRON_JOBS = [
    {"name": "VPN Watchdog",   "schedule": "Every 5 min", "log": os.path.join(LOGS_DIR, "vpn_watchdog.log"), "stale_h": 0.15},
    {"name": "Nuclei Scan",    "schedule": "Nightly 2AM", "log": os.path.join(LOGS_DIR, "nuclei.log"),       "stale_h": 26},
    {"name": "Hunt Engine",    "schedule": "Daily 2PM",   "log": os.path.join(LOGS_DIR, "hunt_engine.log"),  "stale_h": 26},
    {"name": "Katana Crawler", "schedule": "Weekly",      "log": os.path.join(LOGS_DIR, "katana.log"),       "stale_h": 192},
]

# In-memory rolling state (resets on restart — that's fine)
_last_net = {"t": None, "sent": 0, "recv": 0}
_hist_cpu = deque(maxlen=40)
_hist_ram = deque(maxlen=40)


def _net_rate():
    """KB/s up/down based on delta since the previous call."""
    global _last_net
    io  = psutil.net_io_counters()
    now = time.time()
    up = down = 0.0
    if _last_net["t"] is not None:
        dt = now - _last_net["t"]
        if dt > 0:
            up   = (io.bytes_sent - _last_net["sent"]) / dt / 1024.0
            down = (io.bytes_recv - _last_net["recv"]) / dt / 1024.0
    _last_net = {"t": now, "sent": io.bytes_sent, "recv": io.bytes_recv}
    return max(round(up, 1), 0), max(round(down, 1), 0)


def _temp_read():
    try:
        sensors = psutil.sensors_temperatures()
        for key in ("coretemp", "acpitz", "cpu_thermal", "k10temp", "zenpower"):
            if key in sensors and sensors[key]:
                return round(sensors[key][0].current, 1)
    except Exception:
        pass
    return None


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/favicon.ico")
def favicon():
    return ("", 204)


@app.route("/api/stats")
def api_stats():
    cpu  = psutil.cpu_percent(interval=1)
    mem  = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    temp = _temp_read()
    up_kbps, down_kbps = _net_rate()

    _hist_cpu.append(round(cpu, 1))
    _hist_ram.append(round(mem.percent, 1))

    boot = psutil.boot_time()
    up   = datetime.now().timestamp() - boot
    load1, _, _ = os.getloadavg()

    return jsonify({
        "cpu":         round(cpu, 1),
        "ram":         round(mem.percent, 1),
        "ram_used":    round(mem.used / 1e9, 1),
        "ram_total":   round(mem.total / 1e9, 1),
        "disk":        round(disk.percent, 1),
        "disk_used":   round(disk.used / 1e9, 1),
        "disk_total":  round(disk.total / 1e9, 1),
        "temp":        temp,
        "load":        round(load1, 2),
        "uptime":      f"{int(up // 3600)}h {int((up % 3600) // 60)}m",
        "procs":       len(psutil.pids()),
        "up_kbps":     up_kbps,
        "down_kbps":   down_kbps,
        "history_cpu": list(_hist_cpu),
        "history_ram": list(_hist_ram),
    })


@app.route("/api/procs")
def api_procs():
    """Top 5 processes by CPU. Primes cpu_percent, brief sleep, then samples."""
    for p in psutil.process_iter(["name"]):
        try:
            p.cpu_percent()
        except Exception:
            pass
    time.sleep(0.4)
    procs = []
    for p in psutil.process_iter(["name", "memory_percent"]):
        try:
            procs.append({
                "name": (p.info["name"] or "?")[:18],
                "cpu":  round(p.cpu_percent(), 1),
                "mem":  round(p.info["memory_percent"] or 0, 1),
            })
        except Exception:
            pass
    procs.sort(key=lambda x: x["cpu"], reverse=True)
    return jsonify(procs[:5])


@app.route("/api/vpn")
def api_vpn():
    vpn_active, vpn_iface = False, None
    try:
        for name, stats in psutil.net_if_stats().items():
            if any(p in name for p in ("tun", "wg", "vpn", "nordlynx")) and stats.isup:
                vpn_active, vpn_iface = True, name
                break
    except Exception:
        pass
    if not vpn_active:
        try:
            for p in psutil.process_iter(["name"]):
                if p.info["name"] in ("openvpn", "openvpn3", "wg-quick"):
                    vpn_active = True
                    break
        except Exception:
            pass
    return jsonify({"active": vpn_active, "interface": vpn_iface})


@app.route("/api/hunt")
def api_hunt():
    """Reads the most recently modified hunt config JSON for current program info."""
    program, platform_name, status, current_round, last_run = "None", "-", "idle", "-", "-"
    try:
        configs = glob.glob(os.path.join(CONFIG_DIR, "*.json"))
        if configs:
            cfg_path = max(configs, key=os.path.getmtime)
            with open(cfg_path) as f:
                cfg = json.load(f)
            program       = cfg.get("program_name", cfg.get("program", os.path.basename(cfg_path).replace(".json", "")))
            platform_name = cfg.get("platform", "-")
            current_round = cfg.get("current_round", cfg.get("round", "-"))
    except Exception:
        pass

    log = os.path.join(LOGS_DIR, "hunt_engine.log")
    try:
        if os.path.exists(log):
            with open(log, "rb") as f:
                f.seek(0, 2)
                f.seek(max(0, f.tell() - 512))
                last_line = f.readlines()[-1].decode(errors="replace").strip()
            last_run = last_line[:60] if last_line else "-"
            if any(w in last_line.lower() for w in ("running", "start", "request", "testing")):
                status = "running"
    except Exception:
        pass

    return jsonify({
        "program":  program,
        "platform": platform_name,
        "status":   status,
        "round":    current_round,
        "last_run": last_run,
    })


@app.route("/api/crons")
def api_crons():
    now, result = datetime.now().timestamp(), []
    for job in CRON_JOBS:
        last_run, status = "Never", "unknown"
        try:
            if os.path.exists(job["log"]):
                mtime    = os.path.getmtime(job["log"])
                age_h    = (now - mtime) / 3600
                dt       = datetime.fromtimestamp(mtime)
                last_run = dt.strftime("%H:%M") if age_h < 24 else dt.strftime("%b %d %H:%M")
                status   = "ok" if age_h < job["stale_h"] else "stale"
            else:
                status = "missing"
        except Exception:
            status = "error"
        result.append({"name": job["name"], "schedule": job["schedule"], "last_run": last_run, "status": status})
    return jsonify(result)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)