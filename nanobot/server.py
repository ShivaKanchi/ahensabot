import asyncio
from pathlib import Path
from typing import Any

from aiohttp import web
from loguru import logger

from nanobot import __version__
from nanobot.cron.service import CronService
from nanobot.channels.manager import ChannelManager

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ahensa - AI Assistant</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 20px;
            color: #333;
        }

        .hero {
            text-align: center;
            background: white;
            border-radius: 20px;
            padding: 60px 40px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            margin-bottom: 30px;
            max-width: 600px;
            width: 100%;
        }

        .cat-icon {
            font-size: 120px;
            margin-bottom: 20px;
            animation: bounce 2s infinite;
        }

        @keyframes bounce {
            0%, 100% { transform: translateY(0); }
            50% { transform: translateY(-10px); }
        }

        .hero h1 {
            font-size: 48px;
            color: #333;
            margin-bottom: 10px;
        }

        .hero .subtitle {
            font-size: 24px;
            color: #667eea;
            font-weight: 600;
            margin-bottom: 5px;
        }

        .status-message {
            font-size: 18px;
            color: #666;
            margin-top: 20px;
            min-height: 28px;
            font-style: italic;
            transition: opacity 0.3s ease;
        }

        .version {
            font-size: 12px;
            color: #999;
            margin-top: 20px;
        }

        .dashboard {
            background: white;
            border-radius: 20px;
            padding: 40px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            max-width: 900px;
            width: 100%;
        }

        .dashboard h2 {
            font-size: 24px;
            margin-bottom: 20px;
            color: #333;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .refresh-btn {
            cursor: pointer;
            color: #667eea;
            background: #f0f0f0;
            border: none;
            padding: 8px 16px;
            border-radius: 8px;
            font-size: 14px;
            transition: all 0.3s ease;
        }

        .refresh-btn:hover {
            background: #667eea;
            color: white;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
        }

        th, td {
            text-align: left;
            padding: 12px;
            border-bottom: 1px solid #eee;
        }

        th {
            background: #f9f9f9;
            font-weight: 600;
            color: #333;
        }

        .status-ok {
            color: #27ae60;
            font-weight: 600;
        }

        .status-error {
            color: #e74c3c;
            font-weight: 600;
        }

        .info-text {
            color: #666;
            font-style: italic;
        }
    </style>
</head>
<body>
    <div class="hero">
        <div class="cat-icon">🐈‍⬛</div>
        <h1>ahensa</h1>
        <div class="subtitle">Your AI Assistant</div>
        <div class="status-message" id="randomStatus"></div>
        <div class="version">nanobot v{version}</div>
    </div>

    <div class="dashboard">
        <h2>
            Status
            <button class="refresh-btn" onclick="loadData()">🔄 Refresh</button>
        </h2>
        <div id="status">Loading...</div>

        <h2 style="margin-top: 40px;">Scheduled Jobs</h2>
        <div id="cron">Loading...</div>
    </div>

    <script>
        const statuses = [
            "thinking deeply about your request... 🧠",
            "charging up the brain cells ⚡",
            "making sure the vibes are immaculate ✨",
            "plotting world domination (jk) 😹",
            "being absolutely unhinged in the best way 🎭",
            "typing aggressively at my keyboard 💻",
            "convinced i'm the smartest person in the room 🤓",
            "ready to tell you exactly what i think 🗣️",
            "spinning up the gears... beep boop 🤖",
            "manifesting good energy 🔮",
            "procrastinating like a pro 😴",
            "formulating opinions nobody asked for 💭",
            "living my best life (and yours too) 👑",
            "not taking any bullshit 🚫"
        ];

        function getRandomStatus() {
            return statuses[Math.floor(Math.random() * statuses.length)];
        }

        function updateStatusMessage() {
            document.getElementById('randomStatus').textContent = getRandomStatus();
        }

        // Update status message on page load and every 5 seconds
        updateStatusMessage();
        setInterval(updateStatusMessage, 5000);

        async function loadData() {
            try {
                const [statusRes, cronRes] = await Promise.all([
                    fetch('/api/status'),
                    fetch('/api/cron')
                ]);

                const status = await statusRes.json();
                const cron = await cronRes.json();

                renderStatus(status);
                renderCron(cron);
            } catch (e) {
                console.error(e);
                document.getElementById('status').innerHTML = '<p class="info-text">Unable to load status. Is the server running?</p>';
            }
        }

        function renderStatus(data) {
            let html = '<table><tr><th>Component</th><th>Status</th><th>Details</th></tr>';

            // Channels
            if (data.channels && Object.keys(data.channels).length > 0) {
                for (const [name, info] of Object.entries(data.channels)) {
                    const state = info.running ? '<span class="status-ok">✓ Running</span>' : '<span class="status-error">✗ Stopped</span>';
                    html += `<tr><td>Channel: ${name}</td><td>${state}</td><td>${info.enabled ? 'Enabled' : 'Disabled'}</td></tr>`;
                }
            } else {
                 html += `<tr><td>Channels</td><td>-</td><td class="info-text">No channels configured</td></tr>`;
            }

            // Cron
            html += `<tr><td>Cron Service</td><td><span class="status-ok">✓ Active</span></td><td>${data.cron.jobs} job${data.cron.jobs !== 1 ? 's' : ''}</td></tr>`;

            html += '</table>';
            document.getElementById('status').innerHTML = html;
        }

        function renderCron(jobs) {
            if (jobs.length === 0) {
                document.getElementById('cron').innerHTML = '<p class="info-text">No scheduled jobs.</p>';
                return;
            }

            let html = '<table><tr><th>Name</th><th>Schedule</th><th>Next Run</th><th>Last Status</th></tr>';
            for (const job of jobs) {
                const nextRun = job.state.nextRunAtMs
                    ? new Date(job.state.nextRunAtMs).toLocaleString()
                    : 'Thinking...';

                const lastStatus = job.state.lastStatus === 'ok'
                    ? '<span class="status-ok">✓ Success</span>'
                    : (job.state.lastStatus === 'error' ? '<span class="status-error">✗ Error</span>' : '-');

                let schedule = '';
                if (job.schedule.kind === 'every') {
                    schedule = `Every ${job.schedule.everyMs / 1000}s`;
                } else if (job.schedule.kind === 'cron') {
                    schedule = job.schedule.expr;
                } else {
                    schedule = 'One-time';
                }

                html += `<tr>
                    <td>${job.name}</td>
                    <td>${schedule}</td>
                    <td>${nextRun}</td>
                    <td>${lastStatus}</td>
                </tr>`;
            }
            html += '</table>';
            document.getElementById('cron').innerHTML = html;
        }

        loadData();
    </script>
</body>
</html>
"""


class WebServer:
    def __init__(
        self,
        cron_service: CronService,
        channel_manager: ChannelManager,
        port: int = 18790,
    ):
        self.cron_service = cron_service
        self.channel_manager = channel_manager
        self.port = port
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None

    async def start(self) -> None:
        app = web.Application()
        app.router.add_get("/", self._handle_index)
        app.router.add_get("/api/status", self._handle_status)
        app.router.add_get("/api/cron", self._handle_cron)

        self._runner = web.AppRunner(app)
        await self._runner.setup()
        # Bind to localhost for security
        self._site = web.TCPSite(self._runner, "127.0.0.1", self.port)
        await self._site.start()
        logger.info(f"Web server started at http://127.0.0.1:{self.port}")

    async def stop(self) -> None:
        if self._site:
            await self._site.stop()
        if self._runner:
            await self._runner.cleanup()

    async def _handle_index(self, request: web.Request) -> web.Response:
        return web.Response(
            text=HTML_TEMPLATE.replace("{version}", __version__),
            content_type="text/html",
        )

    async def _handle_status(self, request: web.Request) -> web.Response:
        channels_status = self.channel_manager.get_status()
        cron_status = self.cron_service.status()

        return web.json_response(
            {
                "channels": channels_status,
                "cron": cron_status,
            }
        )

    async def _handle_cron(self, request: web.Request) -> web.Response:
        jobs = self.cron_service.list_jobs(include_disabled=True)
        # Convert to dict for JSON serialization
        jobs_data = []
        for j in jobs:
            jobs_data.append(
                {
                    "id": j.id,
                    "name": j.name,
                    "enabled": j.enabled,
                    "schedule": {
                        "kind": j.schedule.kind,
                        "atMs": j.schedule.at_ms,
                        "everyMs": j.schedule.every_ms,
                        "expr": j.schedule.expr,
                    },
                    "state": {
                        "nextRunAtMs": j.state.next_run_at_ms,
                        "lastStatus": j.state.last_status,
                    },
                }
            )

        return web.json_response(jobs_data)
