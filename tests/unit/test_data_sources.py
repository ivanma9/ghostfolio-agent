from ghostfolio_agent.models.api import ChatResponse


def test_chat_response_includes_data_sources_field():
    resp = ChatResponse(
        response="test",
        session_id="s1",
        data_sources=["Finnhub", "Alpha Vantage"],
    )
    assert resp.data_sources == ["Finnhub", "Alpha Vantage"]


def test_chat_response_data_sources_defaults_empty():
    resp = ChatResponse(response="test", session_id="s1")
    assert resp.data_sources == []
