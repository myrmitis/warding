"""junction-client — async Python client for the Junction Gateway.

Usage::

    from junction_client import JunctionClient

    async with JunctionClient(app_name="my-app") as mc:
        ok = await mc.ping()
        status = await mc.get_status()
        await mc.send_message("slot-1", "hello")
"""
from junction_client.client import JunctionClient
from junction_client.errors import JunctionError, ErrorCode

__all__ = ["JunctionClient", "JunctionError", "ErrorCode"]
