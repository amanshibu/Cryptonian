"""Quick verification tests for all 6 improvements."""
import time
from config import Config
from agents.strategy_agent import StrategyAgent
from agents.decision_agent import DecisionAgent
from agents.learning_agent import LearningAgent

c = Config()
sa = StrategyAgent(c)
da = DecisionAgent(c)
la = LearningAgent(c)

passed = 0
failed = 0

def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {name} {detail}")
    else:
        failed += 1
        print(f"  FAIL  {name} {detail}")


print("\n=== Test 1: Spread Filter (Improvement 1) ===")
out = sa.analyze(None, spread_pct=0.5)
check("High spread returns HOLD", out["signal"] == "HOLD", f"reason={out['reason']}")

print("\n=== Test 2: No data returns HOLD ===")
out = sa.analyze(None)
check("None df returns HOLD", out["signal"] == "HOLD")

print("\n=== Test 3: Kill Switch (Improvement 4) ===")
da3 = DecisionAgent(c)
da3.consecutive_losses = 3
da3.kill_switch_activated_at = time.time()
dec = da3.formulate_decision(
    {"signal": "BUY", "reason": "test", "off_session": False}, 100, 1000
)
check("Kill switch blocks BUY", dec["action"] == "HOLD", f"reason={dec['reason']}")

print("\n=== Test 4: Kill Switch Expired ===")
da4 = DecisionAgent(c)
da4.consecutive_losses = 3
da4.kill_switch_activated_at = time.time() - 99999  # long ago
dec2 = da4.formulate_decision(
    {"signal": "BUY", "reason": "test signal", "off_session": False}, 100, 1000
)
check("Kill switch expired allows BUY", dec2["action"] == "BUY", f"reason={dec2['reason']}")

print("\n=== Test 5: Partial TP1 (Improvement 3) ===")
da5 = DecisionAgent(c)
da5.current_position = "LONG"
da5.entry_price = 100.0
da5.position_size_base = 1.0
dec = da5.formulate_decision(
    {"signal": "HOLD", "reason": "", "off_session": False}, 101.5, 1000
)
check("TP1 triggers PARTIAL_SELL", dec["action"] == "PARTIAL_SELL", f"reason={dec['reason']}")
check("TP1 flag set", da5.tp1_hit == True)
check("Position reduced", da5.position_size_base == 0.5, f"remaining={da5.position_size_base}")

print("\n=== Test 6: Full TP2 (Improvement 3) ===")
dec2 = da5.formulate_decision(
    {"signal": "HOLD", "reason": "", "off_session": False}, 104.5, 1000
)
check("TP2 triggers SELL", dec2["action"] == "SELL", f"reason={dec2['reason']}")
check("Position cleared", da5.current_position is None)

print("\n=== Test 7: SL triggers loss streak (Improvement 4) ===")
da7 = DecisionAgent(c)
da7.current_position = "LONG"
da7.entry_price = 100.0
da7.position_size_base = 1.0
dec = da7.formulate_decision(
    {"signal": "HOLD", "reason": "", "off_session": False}, 97.5, 1000
)
check("SL triggers SELL", dec["action"] == "SELL", f"reason={dec['reason']}")
check("Loss streak incremented", da7.consecutive_losses == 1)

print("\n=== Test 8: Learning Agent Adaptive Sizing (Improvement 6) ===")
la8 = LearningAgent(c)
la8.trades = 10
la8.wins = 6
la8.losses = 4
la8.peak_pnl = 100
la8.current_pnl = 40  # 60% drawdown from peak
la8._previous_win_rate = 50
params = la8.get_adaptive_parameters()
check("Drawdown reduces multiplier", params["position_size_multiplier"] < 1.0,
      f"multiplier={params['position_size_multiplier']}")
check("Metrics include streaks", "consecutive_wins" in params["metrics"])
check("Metrics include strategy profit", "profit_by_strategy" in params["metrics"])

print("\n=== Test 9: Off-session size reduction (Improvement 2) ===")
da9 = DecisionAgent(c)
dec = da9.formulate_decision(
    {"signal": "BUY", "reason": "test", "off_session": True}, 100, 1000
)
check("Off-session noted in reason", "Off-session" in dec.get("reason", ""),
      f"reason={dec['reason']}")

print(f"\n{'='*50}")
print(f"Results: {passed} passed, {failed} failed out of {passed+failed} tests")
if failed == 0:
    print("ALL TESTS PASSED")
else:
    print("SOME TESTS FAILED")
