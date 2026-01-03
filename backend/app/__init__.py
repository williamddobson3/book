# App package
import sys
import asyncio

# Fix for Windows asyncio subprocess issues with Playwright
# This must be done before any Playwright imports
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
