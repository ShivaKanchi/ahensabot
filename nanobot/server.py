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
    <title>nanobot Dashboard</title>
    <style>
        body { font-family: system-ui, -apple-system, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; line-height: 1.5; color: #333; }
        h1 { border-bottom: 1px solid #eee; padding-bottom: 10px; }
        h2 { margin-top: 30px; }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        th, td { text-align: left; padding: 8px; border-bottom: 1px solid #eee; }
        th { background: #f9f9f9; }
        .status-ok { color: green; font-weight: bold; }
        .status-error { color: red; font-weight: bold; }
        .refresh { float: right; cursor: pointer; color: #007bff; text-decoration: underline; }
    </style>
</head>
<body>
    <h1>🐈 nanobot <span style="font-size: 0.6em; color: #777;">v{version}</span></h1>

    <h2>Status <span class="refresh" onclick="loadData()">Refresh</span></h2>
    <div id="status">Loading...</div>

    <h2>Scheduled Jobs</h2>
    <div id="cron">Loading...</div>

    <script>
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
                // alert('Failed to load data');
            }
        }

        function renderStatus(data) {
            let html = '<table><tr><th>Component</th><th>Status</th><th>Details</th></tr>';

            // Channels
            if (data.channels && Object.keys(data.channels).length > 0) {
                for (const [name, info] of Object.entries(data.channels)) {
                    const state = info.running ? '<span class="status-ok">Running</span>' : '<span class="status-error">Stopped</span>';
                    html += `<tr><td>Channel: ${name}</td><td>${state}</td><td>${info.enabled ? 'Enabled' : 'Disabled'}</td></tr>`;
                }
            } else {
                 html += `<tr><td>Channels</td><td>-</td><td>No channels configured</td></tr>`;
            }

            // Cron
            html += `<tr><td>Cron Service</td><td><span class="status-ok">Active</span></td><td>${data.cron.jobs} jobs</td></tr>`;

            html += '</table>';
            document.getElementById('status').innerHTML = html;
        }

        function renderCron(jobs) {
            if (jobs.length === 0) {
                document.getElementById('cron').innerHTML = '<p>No scheduled jobs.</p>';
                return;
            }

            let html = '<table><tr><th>Name</th><th>Schedule</th><th>Next Run</th><th>Last Status</th></tr>';
            for (const job of jobs) {
                const nextRun = job.state.nextRunAtMs
                    ? new Date(job.state.nextRunAtMs).toLocaleString()
                    : 'Thinking...';

                const lastStatus = job.state.lastStatus === 'ok'
                    ? '<span class="status-ok">Success</span>'
                    : (job.state.lastStatus === 'error' ? '<span class="status-error">Error</span>' : '-');

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
            content_type="text/html"
        )

    async def _handle_status(self, request: web.Request) -> web.Response:
        channels_status = self.channel_manager.get_status()
        cron_status = self.cron_service.status()

        return web.json_response({
            "channels": channels_status,
            "cron": cron_status,
        })

    async def _handle_cron(self, request: web.Request) -> web.Response:
        jobs = self.cron_service.list_jobs(include_disabled=True)
        # Convert to dict for JSON serialization
        jobs_data = []
        for j in jobs:
            jobs_data.append({
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
                }
            })

        return web.json_response(jobs_data)
