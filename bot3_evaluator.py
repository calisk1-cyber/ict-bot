import os
import json
from datetime import datetime
from base_agent import BaseAgent

class Bot3Evaluator(BaseAgent):
    def __init__(self):
        super().__init__("Bot3-Evaluator")
        self.weights = {
            "sharpe_ratio": 0.30,
            "max_drawdown": 0.25,
            "win_rate": 0.20,
            "profit_factor": 0.15,
            "total_trades": 0.10
        }

    def calculate_score(self, metrics: dict):
        """Calculates a weighted score for a strategy based on its backtest metrics."""
        score = 0
        # Normalize/Scale metrics (Simplified)
        score += metrics.get("sharpe_ratio", 0) * 10 * self.weights["sharpe_ratio"]
        score += (100 - metrics.get("max_drawdown", 100)) / 10 * self.weights["max_drawdown"]
        score += metrics.get("win_rate", 0) / 10 * self.weights["win_rate"]
        score += metrics.get("profit_factor", 0) * 2 * self.weights["profit_factor"]
        score += min(metrics.get("total_trades", 0), 100) / 10 * self.weights["total_trades"]
        return score

    def evaluate_and_select(self):
        """Listens for tested strategies and maintains the active one."""
        self.logger.info("Bot 3 Evaluator is listening for tested strategies...")
        best_active_score = -1
        
        while True:
            try:
                test_result = self.pull_from_queue("strategies:tested")
                if not test_result:
                    self.update_status("Idle: Listening for test results")
                    continue
                
                strat_id = test_result.get("strategy_id")
                if self.is_processed("evaluated_strats", strat_id):
                    self.logger.debug(f"Skipping already evaluated strategy: {strat_id}")
                    continue
                
                strat_name = test_result.get("name", "Unknown")
                self.log_activity(f"Evaluating: {strat_name}")
                metrics = test_result.get("backtest_result", test_result)
                
                if not metrics.get("passed", False):
                    self.mark_as_processed("evaluated_strats", strat_id)
                    self.logger.info(f"Strategy {strat_id} failed backtest. Skipping.")
                    continue
                
                score = self.calculate_score(metrics)
                self.mark_as_processed("evaluated_strats", strat_id)
                self.logger.info(f"Strategy {strat_id} scored: {score:.2f}")
                
                if score > best_active_score:
                    self.logger.info(f"New BEST strategy found! ID: {strat_id} Score: {score:.2f}")
                    best_active_score = score
                    
                    active_info = {
                        "active_strategy_id": strat_id,
                        "activated_at": datetime.utcnow().isoformat(),
                        "score": score,
                        "reason": f"Highest score ({score:.2f}) in recent evaluations",
                        "kill_conditions": { "max_loss_pct": 5, "hours": 72 }
                    }
                    
                    # Push to Active Queue
                    self.push_to_queue("strategy:active", active_info)
                    
            except KeyboardInterrupt:
                break
            except Exception as e:
                self.logger.error(f"Evaluator Error: {e}")

if __name__ == "__main__":
    evaluator = Bot3Evaluator()
    evaluator.evaluate_and_select()
