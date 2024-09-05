from __future__ import annotations

import _thread
import multiprocessing as mp
import queue
import socket
import sys
import tempfile
import time
import warnings
from threading import Event, Thread
from typing import Any, Callable, Dict, List, Tuple
from uuid import uuid4

from .. import core, helpers, optional_features, run
from ..logging import log
from ..server import Server
from . import native

try:
    with warnings.catch_warnings():
        # webview depends on bottle which uses the deprecated CGI function (https://github.com/bottlepy/bottle/issues/1403)
        warnings.filterwarnings('ignore', category=DeprecationWarning)
        import webview
    optional_features.register('webview')
except ModuleNotFoundError:
    pass


class WebviewServer:
    def __init__(self, host: str, port: int, method_queue: mp.Queue, response_queue: mp.Queue) -> None:
        self.host = host
        self.port = port
        self.method_queue = method_queue
        self.response_queue = response_queue

        self._pending_executions: Dict[str, Thread] = {}
        self.main_window: webview.Window = None
        self._main_window_open = Event();
        self._main_window_open.set()

    def _execute(self, thread_name: str, action: str, target: Any, prop_name: str, args: Tuple[Any], kwargs: Dict[str, Any]) -> None:
        try:
            target_obj = None

            match target:
                case None:
                    target_obj = webview

                case 'self':
                    target_obj = self

                case _:
                    if target == -1:
                        target_obj = self.main_window

                    for win in webview.windows:
                        if win.__hash__() == target:
                            target = win
                            break

            res = None

            if not hasattr(target_obj, prop_name):
                raise ValueError(f'property {prop_name} not found')
            
            match action:
                case 'set':
                    if callable(getattr(target_obj, prop_name)):
                        raise ValueError(f'property {prop_name} is not settable')
                    
                    setattr(target_obj, prop_name, args[0])

                case 'get':
                    if callable(getattr(target_obj, prop_name)):
                        raise ValueError(f'property {prop_name} is not settable')

                    res = getattr(target_obj, prop_name)

                case 'call':
                    if not callable(getattr(target_obj, prop_name)):
                        raise ValueError(f'property {prop_name} is not callable')
                    
                    res = getattr(target_obj, prop_name)(*args, **kwargs)

                    pass

            if isinstance(res, webview.Window):
                res = ('window', res.__hash__())
            elif isinstance(res, list):
                res = [(type(r).__name__, r.__hash__()) if isinstance(r, webview.Window) else (type(r).__name__, r) for r in res]
            else:
                res = (type(res).__name__, res)

            self.response_queue.put(res)
        except Exception:
            log.exception(f'error in WebviewServer.{prop_name}')
        finally:
            if thread_name in self._pending_executions:
                self._pending_executions.pop(thread_name)

    def _executor(self) -> None:
        while self._main_window_open.is_set():
            try:
                thread_name = uuid4().hex
                action, target, prop_name, args, kwargs = self.method_queue.get(block=False)

                self._pending_executions[thread_name] = Thread(target=self._execute, args=(thread_name, action, target, prop_name, args, kwargs))
                self._pending_executions[thread_name].start()
            except queue.Empty:
                time.sleep(0.016)
            except Exception:
                log.exception(f'error in WebviewServer.{prop_name}')

    def start(self, title: str, width: int, height: int, fullscreen: bool, frameless: bool) -> None:
        while not helpers.is_port_open(self.host, self.port):
            time.sleep(0.1)

        window_kwargs = {
            'url': f'http://{self.host}:{self.port}',
            'title': title,
            'width': width,
            'height': height,
            'fullscreen': fullscreen,
            'frameless': frameless,
            **core.app.native.window_args,
        }

        webview.settings.update(**core.app.native.settings)

        self.main_window = webview.create_window(**window_kwargs)
        self.main_window.events.closed += self._main_window_open.clear

        Thread(target=self._executor).start()

        webview.start(storage_path=tempfile.mkdtemp(), **core.app.native.start_args)

    def stop(self) -> None:
        if len(self._pending_executions) > 0:
            log.warning('shutdown is possibly blocked by opened dialogs like a file picker')
            while len(self._pending_executions) > 0:
                self._pending_executions.pop(0).join()

    @classmethod
    def start_webview(
        cls,
        host: str, port: int, title: str, width: int, height: int, fullscreen: bool, frameless: bool,
        method_queue: mp.Queue, response_queue: mp.Queue,
    ) -> None:
        server = WebviewServer(host, port, method_queue, response_queue)
        server.start(title, width, height, fullscreen, frameless)

    @classmethod
    def activate(cls, host: str, port: int, title: str, width: int, height: int, fullscreen: bool, frameless: bool) -> None:
        """Activate native mode."""
        def check_shutdown() -> None:
            while process.is_alive():
                time.sleep(0.1)
            Server.instance.should_exit = True
            while not core.app.is_stopped:
                time.sleep(0.1)
            _thread.interrupt_main()

        if not optional_features.has('webview'):
            log.error('Native mode is not supported in this configuration.\n'
                    'Please run "pip install pywebview" to use it.')
            sys.exit(1)

        mp.freeze_support()
        args = host, port, title, width, height, fullscreen, frameless, native.method_queue, native.response_queue
        process = mp.Process(target=WebviewServer.start_webview, args=args, daemon=True)
        process.start()
    
        Thread(target=check_shutdown, daemon=True).start()

    @classmethod
    def find_open_port(cls, start_port: int = 8000, end_port: int = 8999) -> int:
        """Reliably find an open port in a given range.

        This function will actually try to open the port to ensure no firewall blocks it.
        This is better than, e.g., passing port=0 to uvicorn.
        """
        for port in range(start_port, end_port + 1):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(('localhost', port))
                    return port
            except OSError:
                pass
        raise OSError('No open port found')
