# Homeserver Dashboard
Homeserver Dashboard is a self-hosted web app that monitors a 24/7 Ubuntu server in real time — CPU, memory, disk, temperature, network throughput, running processes, scheduled jobs, and VPN status — and pushes phone alerts the moment something goes wrong (disk fills up, VPN drops, a scheduled job stops running). I built it to keep an eye on the infrastructure that runs my automated security research without having to SSH in to check.

How to use it: clone the repo, install Flask and psutil, set your ntfy topic in config.py, then either run python3 dashboard.py or install it as a systemd service so it auto-starts on boot. Open http://<your-server-ip>:5000 in any browser on your local network. Add the monitor script to cron for push alerts.



A lightweight, real-time monitoring dashboard for a self-hosted Linux server. Built to keep an eye on a 24/7 Ubuntu box at a glance — system health, network throughput, running processes, scheduled-job health, and VPN status — with push alerts when something needs attention.

![Homeserver Dashboard](screenshot.png)

## What it does

- Live gauges for CPU, memory, disk, and temperature (auto-refresh every 5s)
- Rolling CPU and memory trend sparklines
- Real-time network throughput (up / down KB/s)
- Top processes by CPU usage
- Scheduled-job (cron) health with last-run timestamps and staleness detection
- VPN interface detection
- Push alerts via [ntfy](https://ntfy.sh) on state changes (disk/temp/memory thresholds, VPN down, stale jobs) — alerts fire only on transitions, so no spam

## Stack

- **Backend:** Python 3, Flask, [psutil](https://github.com/giampaolo/psutil)
- **Frontend:** Vanilla JavaScript, SVG gauges and sparklines — no build step, no framework
- **Deployment:** systemd service, runs on boot
- **Alerts:** ntfy (stdlib `urllib`, no extra dependency)

## Setup

```bash
# Install dependencies
pip install flask psutil

# Configure your alert channel
cp config.example.py config.py
# edit config.py with your ntfy topic

# Run
python3 dashboard.py
```

Open `http://<server-ip>:5000`.

### Run on boot (systemd)

```bash
sudo cp dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now dashboard
```

### Health alerts (cron)

```bash
crontab -e
# every 10 minutes:
*/10 * * * * /usr/bin/python3 /path/to/dashboard_monitor.py >> /path/to/monitor.log 2>&1
```

## Security notes

This dashboard is designed for a **trusted LAN only**. It has no authentication and should **not** be exposed to the public internet. The ntfy topic in `config.py` is a sensitive value (anyone who knows the string can read and publish to the channel) and is gitignored by default.

## License

MIT
