"""Production entrypoint.

Railway execs the startCommand without a shell, so `$PORT` doesn't
expand inline. This script reads PORT from os.getenv, which works under
either bare exec or shell invocation.
"""
import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        log_level=os.getenv("PUBRECORDS_LOG_LEVEL", "info").lower(),
    )
