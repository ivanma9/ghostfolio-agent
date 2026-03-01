import asyncio

import structlog
from langchain_core.tools import tool
from ghostfolio_agent.clients.ghostfolio import GhostfolioClient
from ghostfolio_agent.tools.cache import ttl_cache

logger = structlog.get_logger()


def create_risk_analysis_tool(client: GhostfolioClient):
    @tool
    @ttl_cache(ttl=60)
    async def risk_analysis() -> str:
        """Analyze portfolio risk including concentration risk, sector breakdown, and currency exposure. Use this when the user asks about risk, diversification, sector allocation, or currency exposure."""
        try:
            holdings_data, details_data = await asyncio.gather(
                client.get_portfolio_holdings(),
                client.get_portfolio_details(),
            )
        except Exception as e:
            logger.error("risk_analysis_failed", error=str(e))
            return "Sorry, I couldn't analyze your portfolio risk right now. Please try again later."

        raw_holdings = holdings_data.get("holdings", {}) if isinstance(holdings_data, dict) else {}
        # holdings can be a dict keyed by symbol or a list
        if isinstance(raw_holdings, dict):
            holdings_list_raw = list(raw_holdings.values())
        else:
            holdings_list_raw = list(raw_holdings)

        if not holdings_list_raw:
            return "No holdings data available."

        # Build flat list of holding info
        holding_list = []
        for info in holdings_list_raw:
            if not isinstance(info, dict):
                continue
            holding_list.append({
                "symbol": info.get("symbol", "?"),
                "name": info.get("name", info.get("symbol", "?")),
                "value": info.get("valueInBaseCurrency", 0) or info.get("value", 0) or 0,
                "allocationInPercentage": (info.get("allocationInPercentage", 0) or 0) * 100,
                "currency": info.get("currency", "UNKNOWN"),
                "assetClass": info.get("assetClass", ""),
                "assetSubClass": info.get("assetSubClass", ""),
            })

        # --- Concentration risk ---
        if holding_list:
            top = max(holding_list, key=lambda h: h["allocationInPercentage"])
        else:
            top = None

        conc_lines = ["Concentration Risk:"]
        if top:
            conc_lines.append(f"  Top holding: {top['symbol']} at {top['allocationInPercentage']:.1f}%")
            if top["allocationInPercentage"] > 25:
                conc_lines.append(
                    f"  WARNING: High concentration risk — {top['symbol']} exceeds 25% of portfolio"
                )
        else:
            conc_lines.append("  No holdings found.")

        # --- Sector / asset breakdown ---
        # Try details sectors first
        details = details_data if isinstance(details_data, dict) else {}
        sectors_raw = details.get("sectors", [])

        sector_lines = ["Sector/Asset Breakdown:"]
        if sectors_raw and isinstance(sectors_raw, list):
            for sector in sectors_raw:
                name = sector.get("name", "Unknown")
                pct = (sector.get("allocationInPercentage", 0) or 0) * 100
                sector_lines.append(f"  {name}: {pct:.1f}%")
        else:
            # Fall back to assetClass grouping from holdings
            asset_totals: dict[str, float] = {}
            total_value = sum(h["value"] for h in holding_list)
            for h in holding_list:
                label = h["assetSubClass"] or h["assetClass"] or "Other"
                asset_totals[label] = asset_totals.get(label, 0) + h["value"]
            if total_value > 0:
                for label, val in sorted(asset_totals.items(), key=lambda x: -x[1]):
                    pct = val / total_value * 100
                    sector_lines.append(f"  {label}: {pct:.1f}%")
            else:
                sector_lines.append("  No asset class data available.")

        # --- Currency exposure ---
        currency_totals: dict[str, float] = {}
        for h in holding_list:
            ccy = h["currency"] or "UNKNOWN"
            currency_totals[ccy] = currency_totals.get(ccy, 0) + h["value"]
        total_value = sum(currency_totals.values())

        ccy_lines = ["Currency Exposure:"]
        if total_value > 0:
            for ccy, val in sorted(currency_totals.items(), key=lambda x: -x[1]):
                pct = val / total_value * 100
                ccy_lines.append(f"  {ccy}: {pct:.1f}%")
        else:
            ccy_lines.append("  No currency data available.")

        # --- Summary ---
        num_holdings = len(holding_list)
        top_pct = top["allocationInPercentage"] if top else 0
        num_ccys = len(currency_totals)
        if top_pct > 25:
            risk_level = "high concentration risk"
        elif top_pct > 15:
            risk_level = "moderate concentration risk"
        else:
            risk_level = "well-diversified holdings"

        if top:
            summary = (
                f"Summary: Portfolio has {num_holdings} holdings across {num_ccys} "
                f"currency(ies) with {risk_level} "
                f"(top holding {top['symbol']} at {top_pct:.1f}%)."
            )
        else:
            summary = f"Summary: Portfolio has {num_holdings} holdings across {num_ccys} currency(ies)."

        sections = [
            "Risk Analysis:",
            "",
            "\n".join(conc_lines),
            "",
            "\n".join(sector_lines),
            "",
            "\n".join(ccy_lines),
            "",
            summary,
        ]
        return "\n".join(sections)

    return risk_analysis
