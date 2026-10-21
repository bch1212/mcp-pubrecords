"""Python client for Halverson IQ Data.

Thin httpx wrapper around the REST surface at
https://mcp-pubrecords-production.up.railway.app/tools/*

Pass the per-user API key explicitly. For agentic use, install the MCP
server into Claude directly:
    claude mcp add --transport http halverson-iq-data \\
        https://mcp-pubrecords-production.up.railway.app/mcp/
"""
from .client import PubRecords, PubRecordsAsync, PubRecordsError

__version__ = "0.2.0"
__all__ = ["PubRecords", "PubRecordsAsync", "PubRecordsError", "__version__"]
