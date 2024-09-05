import asyncio
import warnings
from multiprocessing import Queue
from typing import Any, Dict, List, Tuple

from .. import run
from ..logging import log

method_queue: Queue = Queue()
response_queue: Queue = Queue()

try:
    with warnings.catch_warnings():
        # webview depends on bottle which uses the deprecated CGI function (https://github.com/bottlepy/bottle/issues/1403)
        warnings.filterwarnings('ignore', category=DeprecationWarning)
        import webview

    class WebviewProxy():
        def __init__(self, method_queue: Queue, response_queue: Queue) -> None:
            self.method_queue = method_queue
            self.response_queue = response_queue

        async def create_window(
            self,
            title: str,
            url: str | None = None,
            html: str | None = None,
            width: int = 800,
            height: int = 600,
            x: int | None = None,
            y: int | None = None,
            resizable: bool = True,
            fullscreen: bool = False,
            min_size: tuple[int, int] = (200, 100),
            hidden: bool = False,
            frameless: bool = False,
            easy_drag: bool = True,
            shadow: bool = True,
            focus: bool = True,
            minimized: bool = False,
            maximized: bool = False,
            on_top: bool = False,
            confirm_close: bool = False,
            background_color: str = '#FFFFFF',
            transparent: bool = False,
            text_select: bool = False,
            zoomable: bool = False,
            draggable: bool = False,
            vibrancy: bool = False,
        ) -> 'WindowProxy':
            if not url.startswith('http://') and not url.startswith('https://'):
                url = await self.window_call('self', 'get', 'base_url') + url

            return await self.window_call(
                None, 
                'call', 
                'create_window', 
                (), 
                {
                    'title': title, 
                    'url': url, 
                    'html': html, 
                    'width': width, 
                    'height': height, 
                    'x': x, 
                    'y': y, 
                    'resizable': resizable, 
                    'fullscreen': fullscreen, 
                    'min_size': min_size, 
                    'hidden': hidden, 
                    'frameless': frameless, 
                    'easy_drag': easy_drag, 
                    'shadow': shadow, 
                    'focus': focus, 
                    'minimized': minimized, 
                    'maximized': maximized, 
                    'on_top': on_top, 
                    'confirm_close': confirm_close, 
                    'background_color': background_color, 
                    'transparent': transparent, 
                    'text_select': text_select, 
                    'zoomable': zoomable, 
                    'draggable': draggable, 
                    'vibrancy': vibrancy,
                }
            )

        async def window_call(self, window_hash: int, action:str, prop_name: str, args: Tuple = (), kwargs: Dict[str, Any] = {}) -> Any:
            self.method_queue.put((
                action,
                window_hash,
                prop_name, 
                args, 
                kwargs
            ))

            res = await run.io_bound(lambda: self.response_queue.get())

            if res[0] == 'window':
                return WindowProxy(res[1], self)
            elif res[0] == 'list':
                return [WindowProxy(obj[1], self) if obj[0] == 'window' else obj[1] for obj in res[1]]
            else:
                return res[1]

        @property
        async def windows(self) -> List[Any]:
            return await self.window_call(None, 'get', 'windows')
        
        def stop(self) -> None:
            self.method_queue.put((
                'call',
                'self',
                'stop', 
                (), 
                {}
            ))

    class WindowProxy(webview.Window):
        Attributes: List[str] = ['title', 'on_top', 'x', 'y', 'width', 'height']
        Unsupported: List[str] = ['dom']

        def __init__(self, window_hash: int, webview_proxy: WebviewProxy) -> None:
            self._window_hash = window_hash
            self._webview_proxy = webview_proxy

        def __getattribute__(self, name: str) -> Any:
            async def _remote_call(*args: Any, **kwargs: Any) -> Any:
                return await self._webview_proxy.window_call(self._window_hash, 'call', name, args, kwargs)
            
            if name.startswith('_'):
                return super().__getattribute__(name)

            if name in WindowProxy.Attributes:
                return self._webview_proxy.window_call(self._window_hash, 'get', name, (), {})
            elif name in WindowProxy.Unsupported:
                raise AttributeError(f'Attribute {name} is not supported')
            else:
                return _remote_call
            
        def __setattr__(self, name: str, value: Any) -> None:
            if name.startswith('_'):
                return super().__setattr__(name, value)
            
            asyncio.get_running_loop().create_task(self._webview_proxy.window_call(self._window_hash, 'set', name, (value), {}))

except ModuleNotFoundError:
    class WebviewProxy: #type: ignore
        pass # just a dummy if webview is not installed
    class WindowProxy:  # type: ignore
        pass  # just a dummy if webview is not installed
