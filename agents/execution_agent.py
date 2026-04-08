class ExecutionAgent:
    def __init__(self, data_agent, execution_client=None):
        self.data_agent = data_agent
        self.execution_client = execution_client
        self._last_spread_pct = 0.0  # NEW: cached spread for StrategyAgent

    def get_spread_pct(self, symbol):
        """
        NEW: Fetch bid/ask spread as a percentage of mid price.
        Used by the pipeline to feed StrategyAgent's spread filter.
        """
        if self.execution_client:
            self._last_spread_pct = self.execution_client.get_spread_pct(symbol)
        return self._last_spread_pct

    def execute_trade(self, decision):
        """
        Executes the trade on Binance based on the DecisionAgent's output.
        Supports PARTIAL_SELL for multi-level take profit.
        """
        action = decision.get("action")
        amount_usdt = decision.get("amount_usdt", 0)
        symbol = decision.get("target_asset")
        
        if action == "HOLD":
            return {"status": "skipped", "message": "No trade action required."}
            
        # ── NEW: Treat PARTIAL_SELL like SELL for execution ───────────
        is_partial = action == "PARTIAL_SELL"
        effective_action = "SELL" if is_partial else action

        print(f"[ExecutionAgent] Executing {action} for {amount_usdt:.2f} USDT on {symbol}")
        
        try:
            if self.execution_client:
                price = self.execution_client.get_price(symbol)
            else:
                price = 0.0 # Fallback
                
            if price and price > 0:
                amount_base = amount_usdt / price
            else:
                return {"status": "error", "error": "Invalid price"}

            side = 'buy' if effective_action == 'BUY' else 'sell'
            
            if self.execution_client:
                result = self.execution_client.place_order(symbol, side, amount_base)
                if result.get("status") == "success":
                    order = result["order"]
                    order["partial"] = is_partial
                else:
                    return result
            else:
                # Mock fallback
                order = {
                    "id": "MOCK_ORDER_123",
                    "symbol": symbol,
                    "side": side,
                    "amount": amount_base,
                    "price": price,
                    "status": "closed",
                    "partial": is_partial
                }
            
            label = "PARTIAL SELL" if is_partial else side.upper()
            print(f"[ExecutionAgent] Order {label} executed at price {price}.")
            return {"status": "success", "order": order, "decision_context": decision}
            
        except Exception as e:
            print(f"[ExecutionAgent] Failed to execute trade: {e}")
            return {"status": "error", "error": str(e)}
