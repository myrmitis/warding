"""warding-client — async Python client for the Warding Gateway.

Usage::

    from warding_client import WardingClient

    async with WardingClient(app_name="my-app") as mc:
        ok = await mc.ping()
        status = await mc.get_status()
        await mc.send_message("slot-1", "hello")
"""
from warding_client.client import WardingClient
from warding_client.errors import WardingError, ErrorCode

__all__ = ["WardingClient", "WardingError", "ErrorCode"]
