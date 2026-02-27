from ghostfolio_agent.clients.finnhub import FinnhubClient
from ghostfolio_agent.clients.alpha_vantage import AlphaVantageClient
from ghostfolio_agent.clients.fmp import FMPClient


def test_finnhub_client_instantiates():
    client = FinnhubClient(api_key="test")
    assert client._api_key == "test"


def test_alpha_vantage_client_instantiates():
    client = AlphaVantageClient(api_key="test")
    assert client._api_key == "test"


def test_fmp_client_instantiates():
    client = FMPClient(api_key="test")
    assert client._api_key == "test"


def test_clients_are_optional_in_create_tools():
    from unittest.mock import MagicMock
    from ghostfolio_agent.tools import create_tools

    mock_ghostfolio = MagicMock()
    tools = create_tools(client=mock_ghostfolio, finnhub=None, alpha_vantage=None, fmp=None)
    assert isinstance(tools, list)
    assert len(tools) > 0
