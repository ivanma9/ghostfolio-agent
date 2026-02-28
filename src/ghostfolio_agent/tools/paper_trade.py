import json
import os
import pathlib
import re
from datetime import datetime, timezone

from langchain_core.tools import tool
from ghostfolio_agent.clients.ghostfolio import GhostfolioClient

_DATA_FILE = "data/paper_portfolio.json"
_STARTING_CASH = 100_000.0


def _load_portfolio() -> dict:
    os.makedirs("data", exist_ok=True)
    if not pathlib.Path(_DATA_FILE).exists():
        return _default_portfolio()
    with open(_DATA_FILE, "r") as f:
        return json.load(f)


def _save_portfolio(portfolio: dict) -> None:
    os.makedirs("data", exist_ok=True)
    with open(_DATA_FILE, "w") as f:
        json.dump(portfolio, f, indent=2)


def _default_portfolio() -> dict:
    return {
        "cash": _STARTING_CASH,
        "positions": {},
        "trades": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _parse_action(action: str):
    """Return (command, quantity, symbol, is_dollar_amount)."""
    action = action.strip().lower()

    # show / status / reset
    if action in ("show", "status", "show portfolio", "view portfolio", "portfolio"):
        return "show", None, None, False
    if action == "reset":
        return "reset", None, None, False

    # buy/sell with dollar amount: "buy $300 AAPL" or "buy $300 of Micron Technology"
    m = re.match(r"^(buy|sell)\s+\$(\d+(?:\.\d+)?)\s+(?:of\s+)?(.+)$", action)
    if m:
        return m.group(1), float(m.group(2)), m.group(3).strip().upper(), True

    # buy/sell patterns: "buy 10 AAPL" or "buy 10 Micron Technology"
    m = re.match(r"^(buy|sell)\s+(\d+(?:\.\d+)?)\s+(.+)$", action)
    if m:
        return m.group(1), float(m.group(2)), m.group(3).strip().upper(), False

    # buy/sell patterns: "buy AAPL 10"
    m = re.match(r"^(buy|sell)\s+([a-z0-9.\-]+)\s+(\d+(?:\.\d+)?)$", action)
    if m:
        return m.group(1), float(m.group(3)), m.group(2).upper(), False

    return None, None, None, False


def create_paper_trade_tool(client: GhostfolioClient):
    @tool
    async def paper_trade(action: str) -> str:
        """Execute paper trades or view paper portfolio. Actions: 'buy 10 AAPL', 'buy $300 AAPL', 'buy $300 of Micron', 'sell 5 NVDA', 'show portfolio', 'reset'. Accepts tickers or company names, share counts or dollar amounts. Resolves symbols and fetches prices automatically. Starts with $100,000 virtual cash."""
        command, quantity, symbol, is_dollar_amount = _parse_action(action)

        if command is None:
            return (
                "Could not parse action. Use formats like:\n"
                "  buy 10 AAPL\n  sell 5 NVDA\n  show portfolio\n  reset"
            )

        # ── RESET ──────────────────────────────────────────────────────────────
        if command == "reset":
            _save_portfolio(_default_portfolio())
            return f"Paper portfolio reset. Starting cash: ${_STARTING_CASH:,.2f}"

        # ── SHOW ───────────────────────────────────────────────────────────────
        if command == "show":
            portfolio = _load_portfolio()
            cash = portfolio.get("cash", _STARTING_CASH)
            positions = portfolio.get("positions", {})

            lines = ["Paper Portfolio:", f"  Cash: ${cash:,.2f}", ""]
            total_position_value = 0.0
            total_cost_basis = 0.0

            if positions:
                lines.append("Positions:")
                for sym, pos in positions.items():
                    qty = pos.get("quantity", 0)
                    avg_cost = pos.get("avg_cost", 0)
                    current_price = avg_cost  # fallback

                    # Try to get live price
                    try:
                        lookup = await client.lookup_symbol(sym)
                        items = lookup.get("items", [])
                        if items:
                            ds = items[0].get("dataSource", "YAHOO")
                            sym_data = await client.get_symbol(ds, sym)
                            current_price = sym_data.get("marketPrice", avg_cost) or avg_cost
                    except Exception:
                        pass

                    value = qty * current_price
                    cost = qty * avg_cost
                    pnl = value - cost
                    pnl_pct = (pnl / cost * 100) if cost else 0
                    total_position_value += value
                    total_cost_basis += cost
                    sign = "+" if pnl >= 0 else ""
                    lines.append(
                        f"  {sym}: {qty:g} shares, avg cost ${avg_cost:,.2f}, "
                        f"current ${current_price:,.2f}, value ${value:,.2f}, "
                        f"P&L: {sign}${pnl:,.2f} ({sign}{pnl_pct:.1f}%)"
                    )
            else:
                lines.append("Positions: (none)")

            total_value = cash + total_position_value
            total_pnl = total_value - _STARTING_CASH
            total_pnl_pct = (total_pnl / _STARTING_CASH * 100)
            sign = "+" if total_pnl >= 0 else ""
            lines += [
                "",
                f"  Total Value: ${total_value:,.2f} (Cash + Positions)",
                f"  Total P&L:   {sign}${total_pnl:,.2f} ({sign}{total_pnl_pct:.1f}%)",
            ]
            return "\n".join(lines)

        # ── BUY / SELL ─────────────────────────────────────────────────────────
        # Validate symbol and get price
        try:
            lookup = await client.lookup_symbol(symbol)
        except Exception as e:
            return f"Error looking up {symbol}: {e}"

        items = lookup.get("items", [])
        if not items:
            return f"Symbol '{symbol}' not found. Please check the ticker."

        # Prefer USD-denominated equities from YAHOO (US-listed stocks)
        best = items[0]
        for item in items:
            if (
                item.get("currency") == "USD"
                and item.get("assetSubClass") == "STOCK"
                and item.get("dataSource") == "YAHOO"
            ):
                best = item
                break

        data_source = best.get("dataSource", "YAHOO")
        resolved_symbol = best.get("symbol", symbol)

        try:
            sym_data = await client.get_symbol(data_source, resolved_symbol)
        except Exception as e:
            return f"Error fetching price for {resolved_symbol}: {e}"

        price = sym_data.get("marketPrice")
        if not price:
            return (
                f"Could not retrieve current market price for {resolved_symbol}. "
                "Paper trade not executed."
            )

        # Convert dollar amount to share quantity
        if is_dollar_amount:
            dollar_amount = quantity
            quantity = int(dollar_amount / price)  # whole shares only
            if quantity < 1:
                return (
                    f"${dollar_amount:,.2f} is not enough to buy even 1 share of "
                    f"{resolved_symbol} at ${price:,.2f}."
                )

        portfolio = _load_portfolio()
        cash = portfolio["cash"]
        positions = portfolio.setdefault("positions", {})
        trades = portfolio.setdefault("trades", [])

        total_cost = quantity * price

        if command == "buy":
            if cash < total_cost:
                return (
                    f"Insufficient cash. Need ${total_cost:,.2f} but only "
                    f"${cash:,.2f} available."
                )
            # Update position
            if resolved_symbol in positions:
                pos = positions[resolved_symbol]
                old_qty = pos["quantity"]
                old_avg = pos["avg_cost"]
                new_qty = old_qty + quantity
                new_avg = (old_qty * old_avg + quantity * price) / new_qty
                pos["quantity"] = new_qty
                pos["avg_cost"] = new_avg
            else:
                positions[resolved_symbol] = {"quantity": quantity, "avg_cost": price}

            portfolio["cash"] = cash - total_cost
            trades.append({
                "action": "BUY",
                "symbol": resolved_symbol,
                "quantity": quantity,
                "price": price,
                "total": total_cost,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            _save_portfolio(portfolio)
            return (
                f"Paper Trade Executed: BUY {quantity:g} {resolved_symbol} @ ${price:,.2f} = ${total_cost:,.2f}\n"
                f"Cash remaining: ${portfolio['cash']:,.2f}"
            )

        if command == "sell":
            if resolved_symbol not in positions:
                return f"No position in {resolved_symbol}. Cannot sell."
            pos = positions[resolved_symbol]
            owned = pos["quantity"]
            if quantity > owned:
                return (
                    f"Cannot sell {quantity:g} shares of {resolved_symbol}; "
                    f"only {owned:g} owned."
                )
            proceeds = quantity * price
            new_qty = owned - quantity
            if new_qty == 0:
                del positions[resolved_symbol]
            else:
                pos["quantity"] = new_qty

            portfolio["cash"] = cash + proceeds
            trades.append({
                "action": "SELL",
                "symbol": resolved_symbol,
                "quantity": quantity,
                "price": price,
                "total": proceeds,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            _save_portfolio(portfolio)
            return (
                f"Paper Trade Executed: SELL {quantity:g} {resolved_symbol} @ ${price:,.2f} = ${proceeds:,.2f}\n"
                f"Cash remaining: ${portfolio['cash']:,.2f}"
            )

        return "Unrecognised command."

    return paper_trade
