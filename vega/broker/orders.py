"""Order placement, modification, and cancellation."""

from __future__ import annotations

from ..exceptions import OrderError
from ..utils.logging import get_logger
from . import endpoints
from .client import HdfcClient
from .models import Order, OrderResponse, OrderStatus

log = get_logger("orders")


class OrderService:
    """Manages order lifecycle via HDFC Securities API."""

    def __init__(self, client: HdfcClient) -> None:
        self._client = client

    async def place_order(self, order: Order) -> OrderResponse:
        log.info(
            "placing_order",
            ticker=order.ticker,
            side=order.side.value,
            qty=order.quantity,
            order_type=order.order_type.value,
        )
        try:
            payload = {
                "symbol": order.ticker,
                "exchange": order.exchange.value,
                "transactionType": order.side.value,
                "orderType": order.order_type.value,
                "productType": order.product_type.value,
                "quantity": order.quantity,
                "validity": order.validity,
                "disclosedQuantity": order.disclosed_qty,
            }
            if order.price is not None:
                payload["price"] = order.price
            if order.trigger_price is not None:
                payload["triggerPrice"] = order.trigger_price

            data = await self._client.rate_limited_post(
                endpoints.PLACE_ORDER, json=payload
            )

            resp = OrderResponse(
                order_id=str(data.get("orderId", data.get("order_id", ""))),
                status=OrderStatus.PENDING,
                message=data.get("message", "Order placed"),
                ticker=order.ticker,
                side=order.side.value,
                quantity=order.quantity,
                price=order.price or 0.0,
            )
            log.info("order_placed", order_id=resp.order_id, ticker=order.ticker)
            return resp

        except Exception as exc:
            raise OrderError(f"Failed to place order for {order.ticker}: {exc}") from exc

    async def modify_order(
        self, order_id: str, quantity: int | None = None,
        price: float | None = None, trigger_price: float | None = None,
    ) -> OrderResponse:
        log.info("modifying_order", order_id=order_id)
        payload: dict = {}
        if quantity is not None:
            payload["quantity"] = quantity
        if price is not None:
            payload["price"] = price
        if trigger_price is not None:
            payload["triggerPrice"] = trigger_price

        try:
            data = await self._client.put(
                endpoints.MODIFY_ORDER.format(order_id=order_id), json=payload
            )
            return OrderResponse(
                order_id=order_id,
                status=OrderStatus.OPEN,
                message=data.get("message", "Order modified"),
            )
        except Exception as exc:
            raise OrderError(f"Failed to modify order {order_id}: {exc}") from exc

    async def cancel_order(self, order_id: str) -> OrderResponse:
        log.info("cancelling_order", order_id=order_id)
        try:
            data = await self._client.delete(
                endpoints.CANCEL_ORDER.format(order_id=order_id)
            )
            return OrderResponse(
                order_id=order_id,
                status=OrderStatus.CANCELLED,
                message=data.get("message", "Order cancelled"),
            )
        except Exception as exc:
            raise OrderError(f"Failed to cancel order {order_id}: {exc}") from exc

    async def get_order_book(self) -> list[dict]:
        data = await self._client.get(endpoints.ORDER_BOOK)
        return data.get("orders", data.get("data", []))

    async def get_trade_book(self) -> list[dict]:
        data = await self._client.get(endpoints.TRADE_BOOK)
        return data.get("trades", data.get("data", []))
