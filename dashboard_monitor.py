#!/usr/bin/env python3
"""
Homeserver Dashboard — ntfy health monitor
Run on cron (every ~10 min). Pushes to ntfy ONLY when a check changes
state (healthy -> bad, or bad -> recovered), so it won't spam.

Set your topic in config.py:
    NTFY_TOPIC   = "joshuadanielca-alerts-passive-monitoring"
    SERVER_LABEL = "homeserver"
"""
import os, json, time, urllib.request
import psutil

try:
    from config import NTFY_TOPIC, SERVER_LABEL
except ImportError:
    NTFY_TOPIC   = "REPLACE_WITH_YOUR_NTFY_TOPIC"
    SERVER_LABEL = "homeserver"

NTFY_URL   = "https://ntfy.sh/" + NTFY_TOPIC
HERE       = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(HERE, ".monitor_state.json")
LOGS_DIR   = os.path.expanduser("~/hunting/logs")

# Thresholds
DISK_WARN, DISK_HIGH = 90, 95
TEMP_WARN, TEMP_HIGH = 78, 85
MEM_WARN             = 92

# Cron staleness checks: (label, logfile, max_age_hours)
CRON_CHECKS = [
    ("Hunt Engine", os.path.join(LOGS_DIR, "hunt_engine.log"), 26),
    ("Nuclei Scan", os.path.join(LOGS_DIR, "nuclei.log"),      26),
]


def push(title, msg, priority="default", tags=""):
    if "REPLACE" in NTFY_TOPIC:
        print("[skip] ntfy topic not configured:", title)
        return
    req = urllib.request.Request(NTFY_URL, data=msg.encode("utf-8"))
    req.add_header("Title", title)
    req.add_header("Priority", priority)
    if tags:
        req.add_header("Tags", tags)
    try:
        urllib.request.urlopen(req, timeout=10)
        print("[sent]", title)
    except Exception as e:
        print("[fail]", title, "->", e)


def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)
    except Exception:
        pass


def temp_read():
    try:
        s = psutil.sensors_temperatures()
        for k in ("coretemp", "acpitz", "cpu_thermal", "k10temp", "zenpower"):
            if k in s and s[k]:
                return s[k][0].current
    except Exception:
        pass
    return None


def vpn_up():
    try:
        for name, st in psutil.net_if_stats().items():
            if any(p in name for p in ("tun", "wg", "nordlynx")) and st.isup:
                return True
    except Exception:
        pass
    return False


def main():
    state = load_state()
    # checks[key] = (is_bad, title, message, priority, tags)
    checks = {}

    disk = psutil.disk_usage("/").percent
    if disk >= DISK_HIGH:
        checks["disk"] = (True, f"{SERVER_LABEL}: disk critical", f"Disk usage at {disk:.0f}%", "urgent", "floppy_disk,rotating_light")
    elif disk >= DISK_WARN:
        checks["disk"] = (True, f"{SERVER_LABEL}: disk high", f"Disk usage at {disk:.0f}%", "high", "floppy_disk")
    else:
        checks["disk"] = (False, "", "", "", "")

    mem = psutil.virtual_memory().percent
    if mem >= MEM_WARN:
        checks["mem"] = (True, f"{SERVER_LABEL}: memory high", f"Memory usage at {mem:.0f}%", "high", "brain")
    else:
        checks["mem"] = (False, "", "", "", "")

    t = temp_read()
    if t is not None:
        if t >= TEMP_HIGH:
            checks["temp"] = (True, f"{SERVER_LABEL}: temp critical", f"CPU temp {t:.0f}C", "urgent", "fire,rotating_light")
        elif t >= TEMP_WARN:
            checks["temp"] = (True, f"{SERVER_LABEL}: temp high", f"CPU temp {t:.0f}C", "high", "fire")
        else:
            checks["temp"] = (False, "", "", "", "")

    if not vpn_up():
        checks["vpn"] = (True, f"{SERVER_LABEL}: VPN down", "No tun/wg interface is currently up", "high", "lock,warning")
    else:
        checks["vpn"] = (False, "", "", "", "")

    now = time.time()
    for label, logfile, max_age_h in CRON_CHECKS:
        if os.path.exists(logfile):
            age_h = (now - os.path.getmtime(logfile)) / 3600
            bad = age_h > max_age_h
        else:
            bad = True
        key = "cron_" + label.lower().replace(" ", "_")
        if bad:
            checks[key] = (True, f"{SERVER_LABEL}: {label} stale", f"{label} has not run within its expected window", "default", "clock")
        else:
            checks[key] = (False, "", "", "", "")

    # Push only on transitions
    for key, (is_bad, title, msg, prio, tags) in checks.items():
        was_bad = state.get(key, False)
        if is_bad and not was_bad:
            push(title, msg, prio, tags)
        elif was_bad and not is_bad:
            push(f"{SERVER_LABEL}: recovered", f"{key.replace('cron_', '').replace('_', ' ')} back to normal", "low", "white_check_mark")
        state[key] = is_bad

    save_state(state)


if __name__ == "__main__":
    main()