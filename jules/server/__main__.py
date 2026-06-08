"""Entry point for `python -m jules.server`."""
import asyncio

from jules.server.server import main

if __name__ == "__main__":
    asyncio.run(main())
