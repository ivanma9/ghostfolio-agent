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


def test_extract_data_sources_from_tool_outputs():
    from ghostfolio_agent.api.chat import _extract_data_sources

    outputs = [
        "AAPL — Apple Inc.\n  Price: $150.00\n[DATA_SOURCES: Ghostfolio, Finnhub]",
        "Conviction Score: 72/100 — Buy\n[DATA_SOURCES: Finnhub, Alpha Vantage, FMP]",
    ]
    sources = _extract_data_sources(outputs)
    assert sorted(sources) == ["Alpha Vantage", "FMP", "Finnhub", "Ghostfolio"]


def test_extract_data_sources_empty():
    from ghostfolio_agent.api.chat import _extract_data_sources

    assert _extract_data_sources([]) == []
    assert _extract_data_sources(["no metadata here"]) == []


def test_strip_data_sources_line_from_output():
    from ghostfolio_agent.api.chat import _strip_data_sources_line

    output = "AAPL — Apple\n  Price: $150\n[DATA_SOURCES: Finnhub]"
    assert _strip_data_sources_line(output) == "AAPL — Apple\n  Price: $150"
