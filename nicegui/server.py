from __future__ import annotations

import asyncio
import multiprocessing
import socket
from typing import List, Optional

import uvicorn

from . import core, storage
from .native import native
from .run import io_bound


class CustomServerConfig(uvicorn.Config):
    storage_secret: Optional[str] = None
    method_queue: Optional[multiprocessing.Queue] = None
    response_queue: Optional[multiprocessing.Queue] = None


class Server(uvicorn.Server):
    instance: Server

    @classmethod
    def create_singleton(cls, config: CustomServerConfig) -> None:
        """Create a singleton instance of the server."""
        cls.instance = cls(config=config)

    def run(self, sockets: Optional[List[socket.socket]] = None) -> None:
        self.instance = self
        assert isinstance(self.config, CustomServerConfig)
        if self.config.method_queue is not None and self.config.response_queue is not None:
            core.app.native.webview_proxy = native.WebviewProxy(method_queue=self.config.method_queue, response_queue=self.config.response_queue)
            core.app.native.main_window = native.WindowProxy(window_hash=-1, webview_proxy=core.app.native.webview_proxy)
            native.method_queue = self.config.method_queue
            native.response_queue = self.config.response_queue

        storage.set_storage_secret(self.config.storage_secret)
        super().run(sockets=sockets)
