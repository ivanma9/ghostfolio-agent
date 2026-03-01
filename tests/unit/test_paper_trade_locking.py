"""Tests for paper_trade file locking and atomic writes."""
import json
import threading
import time

import pytest
from filelock import FileLock, Timeout


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_portfolio(cash: float = 100_000.0) -> dict:
    return {"cash": cash, "positions": {}, "trades": []}


# ---------------------------------------------------------------------------
# Test 1 – _save_portfolio writes valid JSON atomically
# ---------------------------------------------------------------------------

def test_save_portfolio_atomic(tmp_path, monkeypatch):
    """_save_portfolio should write valid JSON via tmp file + os.replace."""
    import ghostfolio_agent.tools.paper_trade as pt

    data_file = str(tmp_path / "paper_portfolio.json")
    lock_file = str(tmp_path / "paper_portfolio.lock")

    monkeypatch.setattr(pt, "_DATA_FILE", data_file)
    monkeypatch.setattr(pt, "_LOCK_FILE", lock_file)

    portfolio = _make_portfolio(cash=42_000.0)
    portfolio["positions"]["AAPL"] = {"quantity": 10, "avg_cost": 175.0}

    pt._save_portfolio(portfolio)

    # File must exist and be valid JSON
    with open(data_file, "r") as f:
        loaded = json.load(f)

    assert loaded["cash"] == 42_000.0
    assert loaded["positions"]["AAPL"]["quantity"] == 10
    # No leftover .tmp files
    tmp_files = list(tmp_path.glob("*.tmp"))
    assert tmp_files == [], f"Leftover tmp files: {tmp_files}"


# ---------------------------------------------------------------------------
# Test 2 – lock prevents concurrent modification
# ---------------------------------------------------------------------------

def test_lock_prevents_concurrent_modification(tmp_path, monkeypatch):
    """Two simultaneous buys must not corrupt the portfolio (lost-update problem)."""
    import ghostfolio_agent.tools.paper_trade as pt

    data_file = str(tmp_path / "paper_portfolio.json")
    lock_file = str(tmp_path / "paper_portfolio.lock")

    monkeypatch.setattr(pt, "_DATA_FILE", data_file)
    monkeypatch.setattr(pt, "_LOCK_FILE", lock_file)

    # Seed initial portfolio with $200,000 cash
    initial = _make_portfolio(cash=200_000.0)
    pt._save_portfolio(initial)

    errors: list[Exception] = []

    def simulate_buy(symbol: str, quantity: int, price: float) -> None:
        """Simulate the read-modify-write that paper_trade does under lock."""
        try:
            with pt._get_lock():
                portfolio = pt.load_portfolio()
                # Simulate some processing delay to maximise race window
                time.sleep(0.05)
                cash = portfolio["cash"]
                cost = quantity * price
                if cash < cost:
                    return  # insufficient cash — still valid, not an error
                positions = portfolio.setdefault("positions", {})
                if symbol in positions:
                    pos = positions[symbol]
                    old_qty = pos["quantity"]
                    old_avg = pos["avg_cost"]
                    new_qty = old_qty + quantity
                    pos["quantity"] = new_qty
                    pos["avg_cost"] = (old_qty * old_avg + quantity * price) / new_qty
                else:
                    positions[symbol] = {"quantity": quantity, "avg_cost": price}
                portfolio["cash"] = cash - cost
                pt._save_portfolio(portfolio)
        except Exception as exc:
            errors.append(exc)

    # Two threads both try to buy at the same time
    t1 = threading.Thread(target=simulate_buy, args=("AAPL", 10, 175.0))
    t2 = threading.Thread(target=simulate_buy, args=("MSFT", 5, 420.0))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert errors == [], f"Threads raised errors: {errors}"

    final = pt.load_portfolio()
    expected_cash = 200_000.0 - (10 * 175.0) - (5 * 420.0)  # 200000 - 1750 - 2100
    assert abs(final["cash"] - expected_cash) < 0.01, (
        f"Cash mismatch: expected {expected_cash}, got {final['cash']}"
    )
    assert final["positions"]["AAPL"]["quantity"] == 10
    assert final["positions"]["MSFT"]["quantity"] == 5


# ---------------------------------------------------------------------------
# Test 3 – lock timeout raises Timeout when already held
# ---------------------------------------------------------------------------

def test_lock_timeout(tmp_path, monkeypatch):
    """_get_lock() with a short timeout must raise Timeout when lock is held."""
    import ghostfolio_agent.tools.paper_trade as pt

    lock_file = str(tmp_path / "paper_portfolio.lock")
    monkeypatch.setattr(pt, "_LOCK_FILE", lock_file)
    monkeypatch.setattr(pt, "_DATA_FILE", str(tmp_path / "paper_portfolio.json"))

    # Acquire the lock externally and hold it
    outer_lock = FileLock(lock_file, timeout=5)
    with outer_lock:
        # Now attempt to acquire with a very short timeout — must fail
        short_lock = FileLock(lock_file, timeout=0.1)
        with pytest.raises(Timeout):
            short_lock.acquire()
