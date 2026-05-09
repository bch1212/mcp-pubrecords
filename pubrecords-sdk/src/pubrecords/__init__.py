"""PubRecords — Python client for the PubRecords MCP server.

Thin httpx wrapper around the REST surface at
https://mcp-pubrecords-production.up.railway.app/tools/*

For agentic use, install this MCP into Claude directly:
    claude mcp add --transport http pubrecords-mcp \\
        https://mcp-pubrecords-production.up.railway.app/mcp/

This SDK is for non-MCP Python apps that want the same data shape.
"""
from .client import PubRecords, PubRecordsAsync, PubRecordsError

__version__ = "0.1.0"
__all__ = ["PubRecords", "PubRecordsAsync", "PubRecordsError", "__version__"]
