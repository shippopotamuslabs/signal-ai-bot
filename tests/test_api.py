import pytest
from httpx import AsyncClient, ASGITransport
from main import app, handler


@pytest.mark.asyncio
async def test_api_endpoints():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Health check
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"

        # 2. Simulate standard message without trigger
        resp = await client.post("/api/simulate", json={
            "group_id": "test-group-api",
            "sender_name": "Mom",
            "message": "Dinner is at 6pm.",
        })
        assert resp.status_code == 200
        res_data = resp.json()
        assert res_data["ai_reply"] is None

        # 3. Simulate message with @AI trigger
        resp = await client.post("/api/simulate", json={
            "group_id": "test-group-api",
            "sender_name": "Dad",
            "message": "@AI who is cooking dinner?",
        })
        assert resp.status_code == 200
        res_data = resp.json()
        # Since API key is configured, it returns the real LLM reply
        assert res_data["ai_reply"] is not None and len(res_data["ai_reply"]) > 0

        # 4. Check group history
        resp = await client.get("/api/history/test-group-api")
        assert resp.status_code == 200
        hist_data = resp.json()
        assert hist_data["message_count"] == 3  # Mom's msg + Dad's msg + Bot placeholder

        # 5. Clear history
        resp = await client.post("/api/history/test-group-api/clear")
        assert resp.status_code == 200

        resp = await client.get("/api/history/test-group-api")
        assert resp.json()["message_count"] == 0
