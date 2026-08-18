#!/usr/bin/env python3
"""
CLI script to simulate a group chat conversation and test AI triggers and memory.
"""

import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from bot.handler import SignalMessageHandler
from bot.memory import GroupConversationBuffer
from bot.llm_client import OpenRouterClient
from bot.signal_client import SignalClient


class MockSignalClient(SignalClient):
    """Mock client that prints outgoing messages to console instead of sending to Signal."""
    async def send_message(self, message: str, recipients=None, group_id=None):
        print(f"\n📢 [OUTGOING SIGNAL MESSAGE to {recipients or group_id}]:\n{message}\n")
        return {"status": "mock_sent"}


async def main():
    print("=" * 60)
    print("  Signal AI Bot - Interactive Chat Simulator")
    print("=" * 60)
    print("Type family messages to simulate conversation context.")
    print("Include '@AI' at the start of a message to trigger the bot.")
    print("Commands: ':history' (view context), ':clear' (reset buffer), ':exit' (quit)\n")

    handler = SignalMessageHandler(
        signal_client=MockSignalClient(),
    )
    group_id = "family-sim-group"

    while True:
        try:
            line = input("You (Family Member): ").strip()
            if not line:
                continue
            if line in (":exit", "exit", "quit"):
                break
            if line == ":history":
                print("\n--- Current Rolling Buffer ---")
                print(handler.memory.get_formatted_transcript(group_id))
                print("------------------------------\n")
                continue
            if line == ":clear":
                handler.memory.clear(group_id)
                print("[+] Memory buffer cleared.\n")
                continue

            mock_payload = {
                "envelope": {
                    "source": "+15551112233",
                    "sourceNumber": "+15551112233",
                    "sourceName": "Family Member",
                    "dataMessage": {
                        "message": line,
                        "groupInfo": {"groupId": group_id},
                    },
                }
            }

            await handler.handle_incoming_payload(mock_payload)

        except (KeyboardInterrupt, EOFError):
            print("\nExiting simulator.")
            break


if __name__ == "__main__":
    asyncio.run(main())
