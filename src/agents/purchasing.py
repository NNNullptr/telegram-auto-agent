import json
import logging
from src.agents.base_agent import BaseAgent
from src.llm.base import BaseLLM

logger = logging.getLogger(__name__)

# [修改] Function Calling 工具定义：新增 customer_name 字段，用于提取客户名称
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
                "customer_name": {
                    "type": "string",
                    "description": "Customer name provided by the user (e.g. '我叫张三' or '客户名：李四')",
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
    """Handles purchase intent — extracts order via function calling and confirms.

    [修改说明] 下单流程现在会检查客户名称：
    - 如果用户在消息中提到了名字，LLM 通过 extract_order 的 customer_name 字段提取
    - 如果缺少客户名称，bot 会先询问客户名称，暂不生成确认订单
    - 客户提供名称后，再展示完整的确认订单
    """

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
                        f"👤 客户：{order.get('customer_name', '未知')}\n"
                        f"📦 {order['product']} x{order['quantity']}\n"
                        f"💰 总计 ¥{order['total_amount']:.2f}\n"
                        f"正在记录..."
                    ),
                    "order": order,
                    "confirmed": True,
                }

        # [新增] 检查是否正在补充客户名称（上一条 bot 消息在问名字）
        if history and self._is_asking_name(history):
            return self._fill_name_and_confirm(user_message, history)

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

                        # [新增] 如果缺少客户名称，先询问
                        if not order.get("customer_name"):
                            return self._ask_for_name(order)

                        return self._build_confirmation(order)
                    except (json.JSONDecodeError, KeyError) as e:
                        logger.error(f"Failed to parse order: {e}")

        # Fallback: use text response
        reply = response.content or "抱歉，我没能理解您要购买什么。能再说详细点吗？"
        return {"response": reply, "order": None, "confirmed": False}

    @staticmethod
    def _ask_for_name(order: dict) -> dict:
        """[新增] 订单信息已提取但缺少客户名称，向用户询问。

        将订单信息编码在回复文本中（带 [待补充姓名] 标记），
        方便后续从历史中恢复。
        """
        return {
            "response": (
                f"📋 订单信息已收到：\n"
                f"📦 商品：{order['product']}\n"
                f"🔢 数量：{order.get('quantity', 1)}\n"
                f"💵 总计：¥{order['total_amount']:.2f}\n\n"
                f"请问您的姓名是？（用于订单记录）\n"
                f"[待补充姓名]"
            ),
            "order": None,  # 暂不返回 order，等用户补充名字
            "confirmed": False,
        }

    @staticmethod
    def _is_asking_name(history: list[dict[str, str]]) -> bool:
        """[新增] 检查上一条 assistant 消息是否在询问客户姓名。"""
        for msg in reversed(history):
            if msg.get("role") == "assistant":
                return "[待补充姓名]" in msg.get("content", "")
        return False

    @staticmethod
    def _fill_name_and_confirm(user_message: str, history: list[dict[str, str]]) -> dict:
        """[新增] 用户回复了姓名 → 从历史中恢复订单信息 → 生成带姓名的确认消息。"""
        customer_name = user_message.strip()
        # 从历史中找到 [待补充姓名] 的消息，解析订单
        for msg in reversed(history):
            if msg.get("role") == "assistant" and "[待补充姓名]" in msg.get("content", ""):
                content = msg["content"]
                try:
                    order = {}
                    for line in content.split("\n"):
                        if "商品：" in line:
                            order["product"] = line.split("商品：")[1].strip()
                        elif "数量：" in line:
                            order["quantity"] = int(line.split("数量：")[1].strip())
                        elif "总计：¥" in line:
                            total_str = line.split("总计：¥")[1].strip()
                            order["total_amount"] = float(total_str)
                    if "product" in order and "total_amount" in order:
                        order.setdefault("quantity", 1)
                        order["unit_price"] = order["total_amount"] / order["quantity"]
                        order["customer_name"] = customer_name
                        # 生成带姓名的确认消息
                        confirmation_msg = (
                            f"📋 确认订单：\n"
                            f"👤 客户：{customer_name}\n"
                            f"📦 商品：{order['product']}\n"
                            f"🔢 数量：{order['quantity']}\n"
                            f"💰 单价：¥{order['unit_price']:.2f}\n"
                            f"💵 总计：¥{order['total_amount']:.2f}\n\n"
                            f"请回复「确认」下单。"
                        )
                        return {
                            "response": confirmation_msg,
                            "order": order,
                            "confirmed": False,
                        }
                except (ValueError, IndexError):
                    pass
                break

        return {
            "response": "抱歉，订单信息丢失了，请重新下单。",
            "order": None,
            "confirmed": False,
        }

    @staticmethod
    def _build_confirmation(order: dict) -> dict:
        """生成带客户名称的确认消息。"""
        unit_price = order.get("unit_price", 0)
        confirmation_msg = (
            f"📋 确认订单：\n"
            f"👤 客户：{order.get('customer_name', '未知')}\n"
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

    @staticmethod
    def _is_confirmation(user_message: str, history: list[dict[str, str]] | None) -> bool:
        if not history:
            return False
        msg_lower = user_message.strip().lower()
        return any(kw in msg_lower for kw in CONFIRM_KEYWORDS)

    @staticmethod
    def _extract_pending_order(history: list[dict[str, str]] | None) -> dict | None:
        """Look backwards in history for the last order confirmation prompt.

        [修改] 新增解析 '客户：' 行以提取 customer_name。
        """
        if not history:
            return None
        for msg in reversed(history):
            if msg.get("role") == "assistant" and "确认订单" in msg.get("content", ""):
                content = msg["content"]
                try:
                    order = {}
                    for line in content.split("\n"):
                        # [新增] 解析客户名称
                        if "客户：" in line:
                            order["customer_name"] = line.split("客户：")[1].strip()
                        elif "商品：" in line:
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
