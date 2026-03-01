import re

from ghostfolio_agent.models.api import ChatResponse

DATA_SOURCES_RE = re.compile(r"\[DATA_SOURCES:\s*(.+)\]")


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


def test_data_sources_regex_parses():
    line = "[DATA_SOURCES: Finnhub, Alpha Vantage, FMP]"
    m = DATA_SOURCES_RE.search(line)
    assert m is not None
    sources = [s.strip() for s in m.group(1).split(",")]
    assert sources == ["Finnhub", "Alpha Vantage", "FMP"]


def test_data_sources_regex_single():
    line = "[DATA_SOURCES: Finnhub]"
    m = DATA_SOURCES_RE.search(line)
    assert m is not None
    sources = [s.strip() for s in m.group(1).split(",")]
    assert sources == ["Finnhub"]
