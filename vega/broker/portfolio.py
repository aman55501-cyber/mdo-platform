"""Portfolio queries: positions, holdings, funds."""

from __future__ import annotations

from ..utils.logging import get_logger
from . import endpoints
from .client import HdfcClient
from .models import Position, Holding, FundInfo

log = get_logger("portfolio")


class PortfolioService:
    """Queries portfolio state from HDFC Securities API."""

    def __init__(self, client: HdfcClient) -> None:
        self._client = client

    async def get_positions(self) -> list[Position]:
        data = await self._client.get(endpoints.POSITIONS)
        raw = data.get("positions", data.get("data", []))
        positions = []
        for p in raw:
            positions.append(Position(
                ticker=p.get("symbol", p.get("tradingSymbol", "")),
                exchange=p.get("exchange", "NSE"),
                product_type=p.get("productType", p.get("product", "MIS")),
                quantity=int(p.get("quantity", p.get("netQty", 0))),
                average_price=float(p.get("averagePrice", p.get("avgPrice", 0))),
                last_price=float(p.get("lastPrice", p.get("ltp", 0))),
                pnl=float(p.get("pnl", p.get("realizedPnl", 0))),
                day_pnl=float(p.get("dayPnl", p.get("unrealizedPnl", 0))),
            ))
        return positions

    async def get_holdings(self) -> list[Holding]:
        data = await self._client.get(endpoints.HOLDINGS)
        raw = data.get("holdings", data.get("data", []))
        holdings = []
        for h in raw:
            holdings.append(Holding(
                ticker=h.get("symbol", h.get("tradingSymbol", "")),
                exchange=h.get("exchange", "NSE"),
                quantity=int(h.get("quantity", h.get("totalQty", 0))),
                average_price=float(h.get("averagePrice", h.get("avgPrice", 0))),
                last_price=float(h.get("lastPrice", h.get("ltp", 0))),
                pnl=float(h.get("pnl", 0)),
            ))
        return holdings

    async def get_funds(self) -> FundInfo:
        data = await self._client.get(endpoints.FUNDS)
        fund_data = data.get("funds", data.get("data", data))
        if isinstance(fund_data, list) and fund_data:
            fund_data = fund_data[0]
        return FundInfo(
            available=float(fund_data.get("availableMargin", fund_data.get("available", 0))),
            used_margin=float(fund_data.get("usedMargin", fund_data.get("utilized", 0))),
            total=float(fund_data.get("totalBalance", fund_data.get("total", 0))),
        )
