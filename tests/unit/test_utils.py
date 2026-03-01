import pytest
from unittest.mock import AsyncMock, patch

from ghostfolio_agent.utils import safe_fetch


class TestSafeFetch:
    @pytest.mark.asyncio
    async def test_returns_result_on_success(self):
        coro = AsyncMock(return_value={"data": "ok"})
        result = await safe_fetch(coro(), "test_label")
        assert result == {"data": "ok"}

    @pytest.mark.asyncio
    async def test_returns_none_on_exception(self):
        async def failing():
            raise RuntimeError("boom")
        result = await safe_fetch(failing(), "test_label")
        assert result is None

    @pytest.mark.asyncio
    async def test_logs_warning_on_failure(self):
        async def failing():
            raise ValueError("bad value")
        with patch("ghostfolio_agent.utils.logger") as mock_logger:
            result = await safe_fetch(failing(), "my_label")
            assert result is None
            mock_logger.warning.assert_called_once()
            call_args = mock_logger.warning.call_args
            assert call_args[0][0] == "enrichment_fetch_failed"
            assert call_args[1]["label"] == "my_label"
            assert "bad value" in call_args[1]["error"]
