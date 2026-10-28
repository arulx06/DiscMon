from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any


def selector_loop() -> asyncio.AbstractEventLoop:
    return asyncio.SelectorEventLoop()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the DiscMon API on Windows or Linux.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    import uvicorn

    options: dict[str, Any] = {
        "host": args.host,
        "port": args.port,
        "reload": args.reload,
    }
    if sys.platform == "win32":
        # psycopg's async mode cannot run on the Proactor event loop.
        options["loop"] = "app.serve:selector_loop"

    uvicorn.run("app.main:app", **options)


if __name__ == "__main__":
    main()
