import asyncio
import json
import logging
import os
import sys
from typing import Any, Dict, Optional

from bot.handler import SignalMessageHandler
from bot.llm_client import OpenRouterClient
from bot.memory import GroupConversationBuffer
from bot.signal_client import SignalClient
from config import settings

logger = logging.getLogger("signal_bot.native")

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BIN_PATH = os.path.join(BASE_DIR, "bin", "signal-cli")


class NativeSignalSubprocessClient(SignalClient):
    """
    Communicates with signal-cli via stdin/stdout JSON-RPC.
    No networking or Docker required.
    """

    def __init__(self, phone_number: str):
        super().__init__(phone_number=phone_number)
        self.process: Optional[asyncio.subprocess.Process] = None
        self._msg_id = 0
        self._lock = asyncio.Lock()

    async def start_process(self):
        if not os.path.exists(BIN_PATH):
            raise FileNotFoundError(f"Native signal-cli binary not found at: {BIN_PATH}")

        cmd = [BIN_PATH, "-u", self.phone_number, "jsonRpc"]
        logger.info(f"Spawning native signal-cli JSON-RPC process: {' '.join(cmd)}")
        self.process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    async def send_message(self, message: str, recipients=None, group_id=None) -> Dict[str, Any]:
        """Send a message via JSON-RPC write to signal-cli stdin."""
        if not self.process or not self.process.stdin:
            logger.error("Signal process is not running.")
            return {"error": "Process not running"}

        async with self._lock:
            self._msg_id += 1
            cur_id = self._msg_id

            params: Dict[str, Any] = {"message": message}

            if group_id:
                gid = group_id.replace("group.", "")
                params["groupId"] = gid
            elif recipients:
                recip_list = recipients if isinstance(recipients, list) else [recipients]
                # Only treat as group if explicitly prefixed with 'group.'
                if len(recip_list) == 1 and recip_list[0].startswith("group."):
                    params["groupId"] = recip_list[0].replace("group.", "")
                else:
                    params["recipient"] = recip_list
            else:
                logger.error("No recipient or group_id specified.")
                return {"error": "No recipient specified"}

            req = {
                "jsonrpc": "2.0",
                "method": "send",
                "params": params,
                "id": cur_id,
            }

            payload_str = json.dumps(req) + "\n"
            target_dest = params.get("groupId") or params.get("recipient")
            logger.info(f"Dispatching outgoing Signal message to {target_dest}: {message[:50]}...")
            self.process.stdin.write(payload_str.encode("utf-8"))
            await self.process.stdin.drain()

            return {"status": "sent", "id": cur_id}


async def run_native_bot():
    if not settings.SIGNAL_PHONE_NUMBER or settings.SIGNAL_PHONE_NUMBER.startswith("+1555"):
        print("\n[!] Please configure your SIGNAL_PHONE_NUMBER in .env first.")
        print("    Run: python3 scripts/register_number.py")
        return

    if not settings.OPENROUTER_API_KEY or settings.OPENROUTER_API_KEY == "your_openrouter_api_key_here":
        print("\n[!] Warning: OPENROUTER_API_KEY is not set in .env.")
        print("    Bot will respond with placeholder until key is provided in .env.")

    client = NativeSignalSubprocessClient(phone_number=settings.SIGNAL_PHONE_NUMBER)
    await client.start_process()

    handler = SignalMessageHandler(
        signal_client=client,
    )

    print("\n" + "=" * 65)
    print(f"🤖 Signal AI Bot is RUNNING for {settings.SIGNAL_PHONE_NUMBER}")
    print(f"   Model:   {settings.OPENROUTER_MODEL}")
    print(f"   Trigger: {settings.TRIGGER_PREFIX}")
    print(f"   Context: Last {settings.MAX_CONTEXT_MESSAGES} messages retained per group")
    print("=" * 65)
    print("Waiting for messages from your Signal groups... (Press Ctrl+C to stop)\n")

    # Read stdout line-by-line
    while True:
        line = await client.process.stdout.readline()
        if not line:
            break
        raw_str = line.decode("utf-8").strip()
        if not raw_str:
            continue

        try:
            msg = json.loads(raw_str)
            # Check for JSON-RPC receive notification
            if msg.get("method") == "receive":
                params = msg.get("params", {})
                await handler.handle_incoming_payload(params)
            elif "error" in msg:
                logger.error(f"Signal-cli error: {msg['error']}")
        except Exception as e:
            logger.error(f"Error parsing incoming line: {e}", exc_info=True)
