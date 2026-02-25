import asyncio
from pathlib import Path

from aiohttp import web
from loguru import logger

from nanobot import __version__
from nanobot.channels.manager import ChannelManager
from nanobot.cron.service import CronService


def _load_template(name: str) -> str:
    template_path = Path(__file__).parent / "templates" / name
    return template_path.read_text(encoding="utf-8")



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
        self._templates: dict[str, str] = {}

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
        if "index.html" not in self._templates:
            self._templates["index.html"] = await asyncio.to_thread(_load_template, "index.html")

        return web.Response(
            text=self._templates["index.html"].replace("{version}", __version__),
            content_type="text/html"
        )

    async def _handle_status(self, request: web.Request) -> web.Response:
        channels_status = self.channel_manager.get_status()
        cron_status = await self.cron_service.status()

        return web.json_response(
            {
                "channels": channels_status,
                "cron": cron_status,
            }
        )

    async def _handle_cron(self, request: web.Request) -> web.Response:
        jobs = await self.cron_service.list_jobs(include_disabled=True)
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
