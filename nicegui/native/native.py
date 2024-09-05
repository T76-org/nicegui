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

        async def create_window(self, title: str, url: str) -> None:
            if not url.startswith('http://') and not url.startswith('https://'):
                url = await self.window_call('self', 'get', 'base_url') + url

            return await self.window_call(None, 'call', 'create_window', (title, url))

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
