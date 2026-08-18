import time
import pytest
from bot.memory import GroupConversationBuffer, MessageRecord
from bot.handler import SignalMessageHandler
from bot.signal_client import SignalClient
from bot.llm_client import OpenRouterClient
from config import settings


class MockLLM(OpenRouterClient):
    def __init__(self, reply="Mocked AI Answer"):
        super().__init__()
        self.reply = reply
        self.call_count = 0
        self.last_prompt = ""
        self.last_history = ""

    async def generate_response(self, group_id, sender_name, user_prompt, memory):
        self.call_count += 1
        self.last_prompt = user_prompt
        self.last_history = memory.get_formatted_transcript(group_id)
        return self.reply


class MockSignal(SignalClient):
    def __init__(self):
        super().__init__()
        self.sent_messages = []

    async def send_message(self, message: str, recipients=None, group_id=None):
        self.sent_messages.append({"message": message, "recipients": recipients or [group_id]})
        return {"status": "ok"}


def test_memory_buffer_capacity():
    buf = GroupConversationBuffer(max_messages=3)
    group = "test-group"

    buf.add_message(group, "user1", "Message 1")
    buf.add_message(group, "user2", "Message 2")
    buf.add_message(group, "user1", "Message 3")
    assert len(buf.get_history(group)) == 3

    # Add 4th message - 1st should be evicted
    buf.add_message(group, "user3", "Message 4")
    history = buf.get_history(group)
    assert len(history) == 3
    assert history[0].text == "Message 2"
    assert history[1].text == "Message 3"
    assert history[2].text == "Message 4"


def test_memory_name_mapping():
    name_map = {"+15551234": "Mom", "uuid-dad": "Dad"}
    buf = GroupConversationBuffer(max_messages=5, name_map=name_map)

    buf.add_message("g1", "+15551234", "Hello kids")
    buf.add_message("g1", "uuid-dad", "Dinner is ready")
    buf.add_message("g1", "+19998887777", "Random person", profile_name="Uncle Bob")

    history = buf.get_history("g1")
    assert history[0].sender_name == "Mom"
    assert history[1].sender_name == "Dad"
    assert history[2].sender_name == "Uncle Bob"

    transcript = buf.get_formatted_transcript("g1")
    assert "Mom: Hello kids" in transcript
    assert "Dad: Dinner is ready" in transcript
    assert "Uncle Bob: Random person" in transcript


def test_trigger_detection():
    handler = SignalMessageHandler()

    # Valid triggers
    triggered, prompt = handler.is_triggered("@AI what is for dinner?")
    assert triggered is True
    assert prompt == "what is for dinner?"

    # Lowercase trigger
    triggered, prompt = handler.is_triggered("@ai help me with math")
    assert triggered is True
    assert prompt == "help me with math"

    # Leading whitespace
    triggered, prompt = handler.is_triggered("   @AI   recommend a movie")
    assert triggered is True
    assert prompt == "recommend a movie"

    # Just @AI with no prompt
    triggered, prompt = handler.is_triggered("@AI")
    assert triggered is True
    assert len(prompt) > 0

    # Not at the start
    triggered, prompt = handler.is_triggered("Hey @AI check this out")
    assert triggered is False

    # Standard chat message
    triggered, prompt = handler.is_triggered("Can someone pick up milk?")
    assert triggered is False


def test_staleness_check():
    handler = SignalMessageHandler()

    fresh_time = time.time() - 10  # 10s ago
    stale_time = time.time() - (settings.STALE_MESSAGE_THRESHOLD_SECONDS + 50)  # > 120s ago

    assert handler.is_stale(fresh_time) is False
    assert handler.is_stale(stale_time) is True


@pytest.mark.asyncio
async def test_end_to_end_message_flow():
    mock_llm = MockLLM(reply="Spaghetti Bolognese is great for dinner!")
    mock_signal = MockSignal()
    mem = GroupConversationBuffer(max_messages=10, name_map={"+1555111": "Sarah"})

    handler = SignalMessageHandler(
        memory=mem,
        llm_client=mock_llm,
        signal_client=mock_signal,
    )

    group_id = "family-chat-id"

    # 1. Normal message from Sarah (no trigger)
    p1 = {
        "envelope": {
            "source": "+1555111",
            "sourceNumber": "+1555111",
            "timestamp": int(time.time() * 1000),
            "dataMessage": {
                "message": "We have pasta and ground beef in the fridge.",
                "groupInfo": {"groupId": group_id},
            },
        }
    }
    reply1 = await handler.handle_incoming_payload(p1)
    assert reply1 is None
    assert mock_llm.call_count == 0
    assert len(mem.get_history(group_id)) == 1

    # 2. @AI trigger message from Sarah
    p2 = {
        "envelope": {
            "source": "+1555111",
            "sourceNumber": "+1555111",
            "timestamp": int(time.time() * 1000),
            "dataMessage": {
                "message": "@AI what should we make for dinner?",
                "groupInfo": {"groupId": group_id},
            },
        }
    }
    reply2 = await handler.handle_incoming_payload(p2)

    # Verifications
    assert reply2 == "Spaghetti Bolognese is great for dinner!"
    assert mock_llm.call_count == 1
    assert mock_llm.last_prompt == "what should we make for dinner?"
    assert "Sarah: We have pasta and ground beef in the fridge." in mock_llm.last_history

    # Outgoing signal message sent
    assert len(mock_signal.sent_messages) == 1
    assert mock_signal.sent_messages[0]["message"] == "Spaghetti Bolognese is great for dinner!"
    assert mock_signal.sent_messages[0]["recipients"] == [group_id]

    # Check buffer contains bot reply
    history = mem.get_history(group_id)
    assert len(history) == 3  # Msg 1 + Msg 2 + Bot Reply
    assert history[-1].is_bot is True
    assert history[-1].text == "Spaghetti Bolognese is great for dinner!"


@pytest.mark.asyncio
async def test_stale_message_is_buffered_but_not_answered():
    mock_llm = MockLLM()
    mock_signal = MockSignal()
    mem = GroupConversationBuffer(max_messages=10)

    handler = SignalMessageHandler(
        memory=mem,
        llm_client=mock_llm,
        signal_client=mock_signal,
    )

    group_id = "group-offline"
    stale_ts = time.time() - 3600  # 1 hour ago (e.g. laptop closed)

    payload = {
        "envelope": {
            "source": "+1555222",
            "sourceNumber": "+1555222",
            "timestamp": int(stale_ts * 1000),
            "dataMessage": {
                "message": "@AI what is the meaning of life?",
                "groupInfo": {"groupId": group_id},
            },
        }
    }

    reply = await handler.handle_incoming_payload(payload)

    # LLM should not be called and no message sent
    assert reply is None
    assert mock_llm.call_count == 0
    assert len(mock_signal.sent_messages) == 0

    # But message should still be recorded in memory
    assert len(mem.get_history(group_id)) == 1
    assert mem.get_history(group_id)[0].text == "@AI what is the meaning of life?"


@pytest.mark.asyncio
async def test_native_signal_subprocess_client():
    from bot.native_signal_client import NativeSignalSubprocessClient
    import json

    client = NativeSignalSubprocessClient(phone_number="+15551234567")

    class MockStdin:
        def __init__(self):
            self.written = []

        def write(self, data: bytes):
            self.written.append(data.decode("utf-8"))

        async def drain(self):
            pass

    class MockProcess:
        def __init__(self):
            self.stdin = MockStdin()

    client.process = MockProcess()

    # Test sending to 1-on-1 recipient UUID
    res = await client.send_message("Hello there", recipients=["78d26b3b-d09d-4b2b-9f2a-9e3d5a09e25c"])
    assert res["status"] == "sent"
    written_json = json.loads(client.process.stdin.written[0])
    assert written_json["method"] == "send"
    assert written_json["params"]["recipient"] == ["78d26b3b-d09d-4b2b-9f2a-9e3d5a09e25c"]
    assert written_json["params"]["message"] == "Hello there"

    # Test sending to group
    res2 = await client.send_message("Hello group", group_id="group.abc123base64")
    assert res2["status"] == "sent"
    written_json2 = json.loads(client.process.stdin.written[1])
    assert written_json2["method"] == "send"
    assert written_json2["params"]["groupId"] == "abc123base64"

