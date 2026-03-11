import json
import logging
from src.agents.base_agent import BaseAgent
from src.llm.base import BaseLLM

logger = logging.getLogger(__name__)

EXTRACT_ORDER_TOOL = {
    "type": "function",
    "function": {
        "name": "extract_order",
        "description": "Extract structured order details from the user's purchase intent message.",
        "parameters": {
            "type": "object",
            "properties": {
                "product": {
                    "type": "string",
                    "description": "Name of the product the user wants to buy",
                },
                "quantity": {
                    "type": "integer",
                    "description": "Number of items",
                },
                "unit_price": {
                    "type": "number",
                    "description": "Price per unit",
                },
                "total_amount": {
                    "type": "number",
                    "description": "Total transaction amount",
                },
                "description": {
                    "type": "string",
                    "description": "Brief description or notes about the order",
                },
            },
            "required": ["product", "quantity", "total_amount"],
        },
    },
}

CONFIRM_KEYWORDS = {"确认", "是的", "对", "好的", "确定", "yes", "confirm", "ok", "sure", "y"}


class PurchasingAgent(BaseAgent):
    """Handles purchase intent — extracts order via function calling and confirms."""

    def __init__(self, llm: BaseLLM):
        super().__init__(llm, "purchasing.txt")

    async def handle_purchase(
        self,
        user_message: str,
        history: list[dict[str, str]] | None = None,
    ) -> dict:
        """Process a purchase message.

        Returns dict with keys: response, order (dict|None), confirmed (bool).
        """
        # Check if this is a confirmation of a pending order
        if self._is_confirmation(user_message, history):
            order = self._extract_pending_order(history)
            if order:
                return {
                    "response": (
                        f"✅ 订单已确认！\n"
                        f"📦 {order['product']} x{order['quantity']}\n"
                        f"💰 总计 ¥{order['total_amount']:.2f}\n"
                        f"正在记录..."
                    ),
                    "order": order,
                    "confirmed": True,
                }

        # Call LLM with function calling to extract order
        response = await self.llm.chat_with_system(
            system_prompt=self.system_prompt,
            user_message=user_message,
            history=history,
            tools=[EXTRACT_ORDER_TOOL],
        )

        # Parse tool call result
        if response.tool_calls:
            for tc in response.tool_calls:
                if tc["function"]["name"] == "extract_order":
                    try:
                        order = json.loads(tc["function"]["arguments"])
                        unit_price = order.get("unit_price", 0)
                        if not unit_price and order.get("quantity"):
                            unit_price = order["total_amount"] / order["quantity"]
                            order["unit_price"] = unit_price

                        confirmation_msg = (
                            f"📋 确认订单：\n"
                            f"📦 商品：{order['product']}\n"
                            f"🔢 数量：{order['quantity']}\n"
                            f"💰 单价：¥{unit_price:.2f}\n"
                            f"💵 总计：¥{order['total_amount']:.2f}\n\n"
                            f"请回复「确认」下单。"
                        )
                        return {
                            "response": confirmation_msg,
                            "order": order,
                            "confirmed": False,
                        }
                    except (json.JSONDecodeError, KeyError) as e:
                        logger.error(f"Failed to parse order: {e}")

        # Fallback: use text response
        reply = response.content or "抱歉，我没能理解您要购买什么。能再说详细点吗？"
        return {"response": reply, "order": None, "confirmed": False}

    @staticmethod
    def _is_confirmation(user_message: str, history: list[dict[str, str]] | None) -> bool:
        if not history:
            return False
        msg_lower = user_message.strip().lower()
        return any(kw in msg_lower for kw in CONFIRM_KEYWORDS)

    @staticmethod
    def _extract_pending_order(history: list[dict[str, str]] | None) -> dict | None:
        """Look backwards in history for the last order confirmation prompt."""
        if not history:
            return None
        for msg in reversed(history):
            if msg.get("role") == "assistant" and "确认订单" in msg.get("content", ""):
                # Parse order from the confirmation message
                content = msg["content"]
                try:
                    order = {}
                    for line in content.split("\n"):
                        if "商品：" in line:
                            order["product"] = line.split("商品：")[1].strip()
                        elif "数量：" in line:
                            order["quantity"] = int(line.split("数量：")[1].strip())
                        elif "单价：" in line:
                            price_str = line.split("单价：¥")[1].strip()
                            order["unit_price"] = float(price_str)
                        elif "总计：¥" in line:
                            total_str = line.split("总计：¥")[1].strip()
                            order["total_amount"] = float(total_str)
                    if "product" in order and "total_amount" in order:
                        return order
                except (ValueError, IndexError):
                    pass
        return None
