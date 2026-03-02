"""AlertEngine — detects notable portfolio conditions and enforces per-key cooldowns."""

import asyncio
import json
import os
import time
import structlog
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from filelock import FileLock
from ghostfolio_agent.clients.ghostfolio import GhostfolioClient
from ghostfolio_agent.clients.finnhub import FinnhubClient
from ghostfolio_agent.clients.alpha_vantage import AlphaVantageClient
from ghostfolio_agent.clients.fmp import FMPClient
from ghostfolio_agent.clients.congressional import CongressionalClient
from ghostfolio_agent.tools.conviction_score import (
    compute_analyst_score,
    compute_price_target_score,
    compute_sentiment_score,
    compute_earnings_score,
    compute_congressional_score,
    compute_composite,
    score_to_label,
    ANALYST_WEIGHT,
    PRICE_TARGET_WEIGHT,
    SENTIMENT_WEIGHT,
    CONGRESSIONAL_WEIGHT,
    EARNINGS_WEIGHT,
)

@dataclass
class AlertResult:
    symbol: str
    condition: str
    message: str


COOLDOWN_TTL = 86400  # 24 hours in seconds
_COOLDOWN_PATH = Path("data/alert_cooldowns.json")
_COOLDOWN_LOCK = Path("data/alert_cooldowns.lock")

logger = structlog.get_logger()


async def _safe_fetch(coro, label: str):
    """Run a coroutine and return None on any exception."""
    try:
        return await coro
    except Exception as exc:
        logger.warning("alert_fetch_failed", label=label, error=str(exc))
        return None


class AlertEngine:
    """Checks portfolio holdings for notable conditions with cooldown suppression."""

    def __init__(self, cooldown_path: Path | None = None) -> None:
        self._cooldown_path = cooldown_path or _COOLDOWN_PATH
        self._cooldown_lock = Path(str(self._cooldown_path) + ".lock")
        # Maps alert key → unix timestamp when it was last fired
        self._fired: dict[str, float] = self._load_cooldowns()

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _load_cooldowns(self) -> dict[str, float]:
        """Load cooldown state from JSON file. Returns {} on any error."""
        try:
            if not self._cooldown_path.exists():
                return {}
            os.makedirs(self._cooldown_path.parent, exist_ok=True)
            with FileLock(self._cooldown_lock, timeout=10):
                data = json.loads(self._cooldown_path.read_text())
                if isinstance(data, dict):
                    return {k: float(v) for k, v in data.items()}
        except Exception as exc:
            logger.warning("cooldown_load_failed", error=str(exc))
        return {}

    def _save_cooldowns(self) -> None:
        """Persist cooldown state to JSON file."""
        try:
            os.makedirs(self._cooldown_path.parent, exist_ok=True)
            with FileLock(self._cooldown_lock, timeout=10):
                tmp = self._cooldown_path.with_suffix(".tmp")
                tmp.write_text(json.dumps(self._fired))
                os.replace(str(tmp), str(self._cooldown_path))
        except Exception as exc:
            logger.warning("cooldown_save_failed", error=str(exc))

    # ------------------------------------------------------------------
    # Cooldown helpers
    # ------------------------------------------------------------------

    def _is_cooled_down(self, key: str) -> bool:
        """Return True if the alert key has passed its cooldown period (ready to fire)."""
        fired_at = self._fired.get(key)
        if fired_at is None:
            return True
        return (time.time() - fired_at) > COOLDOWN_TTL

    def _record(self, key: str) -> None:
        """Mark an alert key as fired now, and prune expired entries."""
        now = time.time()
        self._fired[key] = now
        # Prune entries older than COOLDOWN_TTL
        expired = [k for k, ts in self._fired.items() if (now - ts) >= COOLDOWN_TTL]
        for k in expired:
            del self._fired[k]
        self._save_cooldowns()

    # ------------------------------------------------------------------
    # Alert condition functions
    # ------------------------------------------------------------------

    def _check_earnings_proximity(
        self,
        symbol: str,
        earnings_data: list[dict] | None,
        today: date,
    ) -> str | None:
        """Alert if earnings are within 3 days (inclusive)."""
        if not earnings_data:
            return None
        for entry in earnings_data:
            date_str = entry.get("date", "")
            try:
                earnings_date = date.fromisoformat(date_str)
                days_until = (earnings_date - today).days
                if 0 <= days_until <= 3:
                    return (
                        f"{symbol} earnings in {days_until} days ({date_str})"
                        " — consider position sizing"
                    )
            except (ValueError, TypeError):
                continue
        return None

    def _check_big_mover(
        self,
        symbol: str,
        quote_data: dict | None,
    ) -> str | None:
        """Alert if |daily % change| >= 5.0."""
        if not quote_data:
            return None
        dp = quote_data.get("dp", 0.0) or 0.0
        price = quote_data.get("c", 0.0) or 0.0
        if abs(dp) < 5.0:
            return None
        direction = "up" if dp > 0 else "down"
        return (
            f"{symbol} {direction} {abs(dp):.1f}% today (${price:.2f})"
            " — significant daily move"
        )

    def _check_analyst_downgrade(
        self,
        symbol: str,
        analyst_data: list[dict] | None,
    ) -> str | None:
        """Alert if bearish (sell + strongSell) >= 50% of total analysts."""
        if not analyst_data:
            return None
        entry = analyst_data[0]
        strong_buy = entry.get("strongBuy", 0)
        buy = entry.get("buy", 0)
        hold = entry.get("hold", 0)
        sell = entry.get("sell", 0)
        strong_sell = entry.get("strongSell", 0)
        total = strong_buy + buy + hold + sell + strong_sell
        if total == 0:
            return None
        bearish = sell + strong_sell
        if bearish / total < 0.5:
            return None
        bullish = strong_buy + buy
        return (
            f"{symbol} analyst consensus shifted to Sell"
            f" ({bullish} of {total} analysts bullish) — monitor closely"
        )

    def _check_congressional_trade(
        self,
        symbol: str,
        summary_data: dict | None,
    ) -> str | None:
        """Alert if any congressional trades in last 3 days for a held symbol."""
        if not summary_data:
            return None
        total = summary_data.get("total_trades", 0)
        if total == 0:
            return None
        buys = summary_data.get("buys", 0)
        sells = summary_data.get("sells", 0)
        sentiment = summary_data.get("sentiment", "N/A")
        return (
            f"{symbol} has {total} congressional trades in the last 3 days"
            f" ({buys} buys, {sells} sells) — {sentiment}"
        )

    async def check_alerts(
        self,
        client: GhostfolioClient,
        user_id: str = "default",
        finnhub: FinnhubClient | None = None,
        alpha_vantage: AlphaVantageClient | None = None,
        fmp: FMPClient | None = None,
        congressional: CongressionalClient | None = None,
    ) -> list[AlertResult]:
        """Run two-phase alert checks across all portfolio holdings.

        Phase 1: parallel quote + earnings + congressional fetch for all symbols.
        Phase 2: for flagged symbols only, fetch analyst/sentiment/price-target data.
        Cooldown suppresses repeat alerts within COOLDOWN_TTL seconds.
        """
        # Short-circuit if no external clients provided
        if finnhub is None and alpha_vantage is None and fmp is None and congressional is None:
            return []

        # Fetch holdings
        try:
            holdings_resp = await client.get_portfolio_holdings()
        except Exception as exc:
            logger.warning("alert_holdings_fetch_failed", error=str(exc))
            return []

        holdings: dict = holdings_resp.get("holdings", {})
        if not holdings:
            return []

        symbols = list(holdings.keys())
        alerts: list[AlertResult] = []
        today = date.today()

        # ------------------------------------------------------------------
        # Phase 1: parallel quote + earnings + congressional for all symbols
        # ------------------------------------------------------------------
        phase1_tasks: list = []
        phase1_meta: list[tuple[str, str]] = []  # (symbol, data_type)

        for sym in symbols:
            if finnhub is not None:
                phase1_tasks.append(_safe_fetch(finnhub.get_quote(sym), f"quote:{sym}"))
                phase1_meta.append((sym, "quote"))
                phase1_tasks.append(_safe_fetch(finnhub.get_earnings_calendar(sym), f"earnings:{sym}"))
                phase1_meta.append((sym, "earnings"))
            if congressional is not None:
                phase1_tasks.append(_safe_fetch(congressional.get_trades_summary(ticker=sym, days=3), f"cong:{sym}"))
                phase1_meta.append((sym, "congressional"))

        phase1_results = await asyncio.gather(*phase1_tasks) if phase1_tasks else []

        # Unpack phase 1 results into per-symbol maps
        quotes: dict[str, dict | None] = {sym: None for sym in symbols}
        earnings_map: dict[str, list | None] = {sym: None for sym in symbols}
        congressional_map: dict[str, dict | None] = {sym: None for sym in symbols}

        for (sym, data_type), result in zip(phase1_meta, phase1_results):
            if data_type == "quote":
                quotes[sym] = result
            elif data_type == "earnings":
                earnings_map[sym] = result
            elif data_type == "congressional":
                congressional_map[sym] = result

        # Evaluate phase 1 conditions; collect flagged symbols for phase 2
        flagged_symbols: set[str] = set()
        for sym in symbols:
            earnings_result = self._check_earnings_proximity(sym, earnings_map.get(sym), today)
            key = f"{sym}:earnings"
            if earnings_result and self._is_cooled_down(key):
                alerts.append(AlertResult(symbol=sym, condition="earnings_proximity", message=earnings_result))
                self._record(key)
                flagged_symbols.add(sym)

            big_mover_result = self._check_big_mover(sym, quotes.get(sym))
            key = f"{sym}:big_mover"
            if big_mover_result and self._is_cooled_down(key):
                alerts.append(AlertResult(symbol=sym, condition="big_mover", message=big_mover_result))
                self._record(key)
                flagged_symbols.add(sym)

            congressional_result = self._check_congressional_trade(sym, congressional_map.get(sym))
            key = f"{sym}:congressional_trade"
            if congressional_result and self._is_cooled_down(key):
                alerts.append(AlertResult(symbol=sym, condition="congressional_trade", message=congressional_result))
                self._record(key)
                flagged_symbols.add(sym)

        # ------------------------------------------------------------------
        # Phase 2: deeper enrichment for flagged symbols only
        # ------------------------------------------------------------------
        if not flagged_symbols:
            return alerts

        phase2_tasks: list = []
        phase2_meta: list[tuple[str, str]] = []  # (symbol, data_type)

        for sym in flagged_symbols:
            if finnhub is not None:
                phase2_tasks.append(
                    _safe_fetch(
                        finnhub.get_analyst_recommendations(sym), f"analyst:{sym}"
                    )
                )
                phase2_meta.append((sym, "analyst"))

            if alpha_vantage is not None:
                phase2_tasks.append(
                    _safe_fetch(
                        alpha_vantage.get_news_sentiment(sym), f"news:{sym}"
                    )
                )
                phase2_meta.append((sym, "news"))

            if fmp is not None:
                phase2_tasks.append(
                    _safe_fetch(
                        fmp.get_price_target_consensus(sym), f"pt:{sym}"
                    )
                )
                phase2_meta.append((sym, "price_target"))

        phase2_results = await asyncio.gather(*phase2_tasks) if phase2_tasks else []

        # Collect phase 2 data per symbol
        analyst_map: dict[str, list | None] = {sym: None for sym in flagged_symbols}
        news_map: dict[str, list | None] = {sym: None for sym in flagged_symbols}
        pt_map: dict[str, list | None] = {sym: None for sym in flagged_symbols}

        for (sym, data_type), result in zip(phase2_meta, phase2_results):
            if data_type == "analyst":
                analyst_map[sym] = result
            elif data_type == "news":
                news_map[sym] = result
            elif data_type == "price_target":
                pt_map[sym] = result

        # Evaluate phase 2 conditions
        for sym in flagged_symbols:
            market_price = (quotes.get(sym) or {}).get("c", 0.0) or 0.0

            analyst_result = self._check_analyst_downgrade(sym, analyst_map.get(sym))
            key = f"{sym}:analyst_downgrade"
            if analyst_result and self._is_cooled_down(key):
                alerts.append(AlertResult(symbol=sym, condition="analyst_downgrade", message=analyst_result))
                self._record(key)

            conviction_result = self._check_low_conviction(
                symbol=sym,
                analyst_data=analyst_map.get(sym),
                pt_data=pt_map.get(sym),
                news_data=news_map.get(sym),
                earnings_data=earnings_map.get(sym),
                market_price=market_price,
                congressional_data=congressional_map.get(sym),
            )
            key = f"{sym}:low_conviction"
            if conviction_result and self._is_cooled_down(key):
                alerts.append(AlertResult(symbol=sym, condition="low_conviction", message=conviction_result))
                self._record(key)

        return alerts

    def _check_low_conviction(
        self,
        symbol: str,
        analyst_data: list[dict] | None,
        pt_data: list[dict] | None,
        news_data: list[dict] | None,
        earnings_data: list[dict] | None,
        market_price: float,
        congressional_data: dict | None = None,
    ) -> str | None:
        """Alert if composite conviction score < 40."""
        components = []

        analyst_score, analyst_expl = compute_analyst_score(analyst_data)
        if analyst_score is not None:
            components.append(("analyst", analyst_score, analyst_expl, ANALYST_WEIGHT))

        pt_score, pt_expl = compute_price_target_score(pt_data, market_price)
        if pt_score is not None:
            components.append(("price_target", pt_score, pt_expl, PRICE_TARGET_WEIGHT))

        sent_score, sent_expl = compute_sentiment_score(news_data)
        if sent_score is not None:
            components.append(("sentiment", sent_score, sent_expl, SENTIMENT_WEIGHT))

        cong_score, cong_expl = compute_congressional_score(congressional_data)
        if cong_score is not None:
            components.append(("congressional", cong_score, cong_expl, CONGRESSIONAL_WEIGHT))

        earn_score, earn_expl = compute_earnings_score(earnings_data)
        components.append(("earnings", earn_score, earn_expl, EARNINGS_WEIGHT))

        # Need at least one non-earnings component
        non_earnings = [c for c in components if c[0] != "earnings"]
        if not non_earnings:
            return None

        composite, label, _ = compute_composite(components)
        if composite is None or composite >= 40:
            return None

        return (
            f"{symbol} conviction score dropped to {composite}/100 ({label})"
            " — review position"
        )
