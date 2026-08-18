#!/usr/bin/env python3
"""
Main launcher to run the Signal AI Bot natively on your laptop.
"""

import asyncio
import logging
from bot.native_signal_client import run_native_bot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

if __name__ == "__main__":
    try:
        asyncio.run(run_native_bot())
    except KeyboardInterrupt:
        print("\n[!] Signal AI Bot stopped.")
