"""Tests for benchmark_comparison tool."""

import pytest
from datetime import date, timedelta
from unittest.mock import AsyncMock

from ghostfolio_agent.clients.ghostfolio import GhostfolioClient
from ghostfolio_agent.tools.benchmark_comparison import create_benchmark_comparison_tool
from ghostfolio_agent.tools.cache import clear_all_caches


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear TTL cache before each test to avoid cross-test contamination."""
    clear_all_caches()
    yield
    clear_all_caches()


@pytest.fixture
def mock_client():
    client = AsyncMock(spec=GhostfolioClient)
    client.get_benchmarks.return_value = {
        "benchmarks": [
            {
                "dataSource": "YAHOO",
                "symbol": "SPY",
                "name": "S&P 500",
                "marketCondition": "NEUTRAL_MARKET",
                "performances": {
                    "allTimeHigh": {
                        "date": "2025-02-19T00:00:00.000Z",
                        "performancePercent": -0.05,
                    }
                },
                "trend50d": "UP",
                "trend200d": "UP",
            }
        ]
    }
    client.get_benchmark_detail.return_value = {
        "marketData": [
            {"date": "2025-01-02", "value": 0},
            {"date": "2025-06-15", "value": 9.8},
        ]
    }
    client.get_portfolio_performance.return_value = {
        "performance": {
            "netPerformancePercentage": 0.123,
            "netPerformance": 8450.0,
            "currentNetWorth": 77000.0,
        }
    }
    return client


@pytest.fixture
def tool(mock_client):
    return create_benchmark_comparison_tool(mock_client)


# ---------------------------------------------------------------------------
# 1. Basic comparison — all data present
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_basic_comparison(tool):
    result = await tool.ainvoke({"benchmark": "SPY", "period": "ytd"})
    assert "Market Context" in result
    assert "Performance Comparison" in result
    assert "Alpha" in result
    assert "[DATA_SOURCES: Ghostfolio]" in result


# ---------------------------------------------------------------------------
# 2. Default params
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_default_params(tool, mock_client):
    result = await tool.ainvoke({})
    # Should use SPY and ytd by default
    assert "SPY" in result
    assert "YTD" in result
    # get_portfolio_performance should be called with "ytd"
    mock_client.get_portfolio_performance.assert_called_once_with("ytd")


# ---------------------------------------------------------------------------
# 3. Custom benchmark
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_custom_benchmark(mock_client):
    mock_client.get_benchmarks.return_value = {
        "benchmarks": [
            {
                "dataSource": "YAHOO",
                "symbol": "QQQ",
                "name": "Nasdaq 100",
                "marketCondition": "NEUTRAL_MARKET",
                "performances": {"allTimeHigh": {"performancePercent": -0.03}},
                "trend50d": "UP",
                "trend200d": "DOWN",
            }
        ]
    }
    mock_client.get_benchmark_detail.return_value = {
        "marketData": [
            {"date": "2025-01-02", "value": 0},
            {"date": "2025-06-15", "value": 12.5},
        ]
    }
    tool = create_benchmark_comparison_tool(mock_client)
    result = await tool.ainvoke({"benchmark": "QQQ", "period": "ytd"})
    assert "QQQ" in result
    assert "Nasdaq 100" in result


# ---------------------------------------------------------------------------
# 4. Benchmark not found
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_benchmark_not_found(tool):
    result = await tool.ainvoke({"benchmark": "INVALID", "period": "ytd"})
    assert "not available" in result.lower()
    assert "S&P 500" in result
    assert "SPY" in result


# ---------------------------------------------------------------------------
# 5. Period ytd → start_date = Jan 1 of current year
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_period_ytd_start_date(tool, mock_client):
    await tool.ainvoke({"benchmark": "SPY", "period": "ytd"})
    expected_start = date(date.today().year, 1, 1).isoformat()
    mock_client.get_benchmark_detail.assert_called_once()
    call_args = mock_client.get_benchmark_detail.call_args
    assert call_args.args[2] == expected_start or call_args.kwargs.get("start_date") == expected_start or call_args[0][2] == expected_start


# ---------------------------------------------------------------------------
# 6. Period 1y → start_date ~365 days ago
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_period_1y_start_date(tool, mock_client):
    await tool.ainvoke({"benchmark": "SPY", "period": "1y"})
    expected_start = (date.today() - timedelta(days=365)).isoformat()
    mock_client.get_benchmark_detail.assert_called_once()
    call_args = mock_client.get_benchmark_detail.call_args
    actual_start = call_args.args[2] if len(call_args.args) > 2 else call_args[0][2]
    assert actual_start == expected_start


# ---------------------------------------------------------------------------
# 7. Period max → start_date = "2000-01-01"
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_period_max_start_date(tool, mock_client):
    await tool.ainvoke({"benchmark": "SPY", "period": "max"})
    mock_client.get_benchmark_detail.assert_called_once()
    call_args = mock_client.get_benchmark_detail.call_args
    actual_start = call_args.args[2] if len(call_args.args) > 2 else call_args[0][2]
    assert actual_start == "2000-01-01"


# ---------------------------------------------------------------------------
# 8. Benchmark detail failure → still shows Market Context, no Performance Comparison
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_benchmark_detail_failure(mock_client):
    mock_client.get_benchmark_detail.side_effect = Exception("detail failed")
    tool = create_benchmark_comparison_tool(mock_client)
    result = await tool.ainvoke({"benchmark": "SPY", "period": "ytd"})
    assert "Market Context" in result
    # No benchmark timeline section
    assert "Benchmark Timeline" not in result
    # Should still show portfolio performance if available
    assert "[DATA_SOURCES: Ghostfolio]" in result


# ---------------------------------------------------------------------------
# 9. Portfolio performance failure → still shows benchmark return data
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_portfolio_failure(mock_client):
    mock_client.get_portfolio_performance.side_effect = Exception("portfolio failed")
    tool = create_benchmark_comparison_tool(mock_client)
    result = await tool.ainvoke({"benchmark": "SPY", "period": "ytd"})
    assert "Market Context" in result
    assert "S&P 500" in result
    # Should show benchmark timeline
    assert "Benchmark Timeline" in result
    # Should NOT have "Your Portfolio" line
    assert "Your Portfolio" not in result


# ---------------------------------------------------------------------------
# 10. Both benchmark detail + portfolio fail → only Market Context shown
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_both_detail_and_portfolio_fail(mock_client):
    mock_client.get_benchmark_detail.side_effect = Exception("detail failed")
    mock_client.get_portfolio_performance.side_effect = Exception("portfolio failed")
    tool = create_benchmark_comparison_tool(mock_client)
    result = await tool.ainvoke({"benchmark": "SPY", "period": "ytd"})
    assert "Market Context" in result
    assert "Performance Comparison" not in result
    assert "Benchmark Timeline" not in result
    assert "[DATA_SOURCES: Ghostfolio]" in result


# ---------------------------------------------------------------------------
# 11. Alpha positive → "outperforming"
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_alpha_positive(mock_client):
    # Portfolio 12.3% vs benchmark 9.8% → outperforming
    mock_client.get_portfolio_performance.return_value = {
        "performance": {
            "netPerformancePercentage": 0.123,
            "netPerformance": 8450.0,
            "currentNetWorth": 77000.0,
        }
    }
    mock_client.get_benchmark_detail.return_value = {
        "marketData": [
            {"date": "2025-01-02", "value": 0},
            {"date": "2025-06-15", "value": 9.8},
        ]
    }
    tool = create_benchmark_comparison_tool(mock_client)
    result = await tool.ainvoke({"benchmark": "SPY", "period": "ytd"})
    assert "outperforming" in result


# ---------------------------------------------------------------------------
# 12. Alpha negative → "underperforming"
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_alpha_negative(mock_client):
    # Portfolio 5.0% vs benchmark 9.8% → underperforming
    mock_client.get_portfolio_performance.return_value = {
        "performance": {
            "netPerformancePercentage": 0.05,
            "netPerformance": 3000.0,
            "currentNetWorth": 77000.0,
        }
    }
    mock_client.get_benchmark_detail.return_value = {
        "marketData": [
            {"date": "2025-01-02", "value": 0},
            {"date": "2025-06-15", "value": 9.8},
        ]
    }
    tool = create_benchmark_comparison_tool(mock_client)
    result = await tool.ainvoke({"benchmark": "SPY", "period": "ytd"})
    assert "underperforming" in result


# ---------------------------------------------------------------------------
# 13. Alpha zero → "matching"
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_alpha_zero(mock_client):
    # Portfolio == benchmark (both 9.8%)
    mock_client.get_portfolio_performance.return_value = {
        "performance": {
            "netPerformancePercentage": 0.098,
            "netPerformance": 5000.0,
            "currentNetWorth": 77000.0,
        }
    }
    mock_client.get_benchmark_detail.return_value = {
        "marketData": [
            {"date": "2025-01-02", "value": 0},
            {"date": "2025-06-15", "value": 9.8},
        ]
    }
    tool = create_benchmark_comparison_tool(mock_client)
    result = await tool.ainvoke({"benchmark": "SPY", "period": "ytd"})
    assert "matching" in result


# ---------------------------------------------------------------------------
# 14. Data sources tag always present
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_data_sources_tag(tool):
    result = await tool.ainvoke({"benchmark": "SPY", "period": "ytd"})
    assert result.strip().endswith("[DATA_SOURCES: Ghostfolio]")


# ---------------------------------------------------------------------------
# 15. Market condition display mapping
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_market_condition_display(mock_client):
    for raw, expected in [
        ("NEUTRAL_MARKET", "Neutral Market"),
        ("BEAR_MARKET", "Bear Market"),
        ("ALL_TIME_HIGH", "All-Time High"),
    ]:
        clear_all_caches()
        mock_client.get_benchmarks.return_value = {
            "benchmarks": [
                {
                    "dataSource": "YAHOO",
                    "symbol": "SPY",
                    "name": "S&P 500",
                    "marketCondition": raw,
                    "performances": {"allTimeHigh": {"performancePercent": -0.05}},
                    "trend50d": "UP",
                    "trend200d": "UP",
                }
            ]
        }
        tool = create_benchmark_comparison_tool(mock_client)
        result = await tool.ainvoke({"benchmark": "SPY", "period": "ytd"})
        assert expected in result, f"Expected '{expected}' in output for condition {raw}"


# ---------------------------------------------------------------------------
# 16. Timeline sampling — 30 data points → ~10 sampled
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_timeline_sampling(mock_client):
    # Create 30 data points
    market_data = [
        {"date": f"2025-{(i // 30 + 1):02d}-{(i % 28 + 1):02d}", "value": float(i)}
        for i in range(30)
    ]
    mock_client.get_benchmark_detail.return_value = {"marketData": market_data}
    tool = create_benchmark_comparison_tool(mock_client)
    result = await tool.ainvoke({"benchmark": "SPY", "period": "ytd"})
    assert "Benchmark Timeline" in result
    # Count timeline lines — each looks like "  2025-...:  SPY ..."
    timeline_lines = [
        line for line in result.splitlines()
        if line.strip().startswith("2025-") and "SPY" in line
    ]
    # Should be ~10 (at most 10)
    assert len(timeline_lines) <= 10
    assert len(timeline_lines) >= 2  # at least first and last


# ---------------------------------------------------------------------------
# 17. ATH distance display — -0.05 → "5.0% from ATH"
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ath_distance_display(tool):
    result = await tool.ainvoke({"benchmark": "SPY", "period": "ytd"})
    assert "5.0% from ATH" in result


# ---------------------------------------------------------------------------
# 18. Benchmarks fetch failure → user-friendly error
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_benchmarks_fetch_failure(mock_client):
    mock_client.get_benchmarks.side_effect = Exception("benchmarks API down")
    tool = create_benchmark_comparison_tool(mock_client)
    result = await tool.ainvoke({"benchmark": "SPY", "period": "ytd"})
    # Should return user-friendly error, not raise
    assert "sorry" in result.lower() or "couldn't" in result.lower() or "error" in result.lower()
    # Should NOT contain traceback or raw exception
    assert "Traceback" not in result
    assert "benchmarks API down" not in result
