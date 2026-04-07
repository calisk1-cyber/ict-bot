import os
import json
import logging
import time
import random
from datetime import datetime
from base_agent import BaseAgent
from db_models import BacktestResult, LiveTrade
import openai

class Bot5Analyst(BaseAgent):
    def __init__(self):
        super().__init__("Bot2-Hunter") # Using Hunter ID for shared research capabilities or its own
        self.name = "Bot5-Analyst"
        self.rules_file = "/root/bot/dynamic_rules.json"
        if not os.path.exists("/root/bot"): os.makedirs("/root/bot") # Ensure path on VPS
        
        # Default local rules if VPS path fails during local dev
        if not os.path.exists(os.path.dirname(self.rules_file)):
            self.rules_file = "dynamic_rules.json"

        self.openai_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def research_hft_best_practices(self):
        """
        Simulates autonomous research by pulling latest HFT/Scalper optimization trends.
        In a full version, this would use a Web Search tool or ArXiv.
        """
        self.logger.info("Bot 5: Starting autonomous HFT research...")
        # For now, we simulate the findings or use the LLM to generate them based on general knowledge
        # because we are in a loop.
        prompt = "Act as a Senior HFT Quant. Research the latest 2024-2025 best practices for minimizing broker fees and smoothing drawdowns in high-frequency scalping bots. Output 3 concise actionable rules."
        
        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}]
            )
            findings = response.choices[0].message.content
            self.logger.info(f"Research Findings: {findings}")
            return findings
        except Exception as e:
            self.logger.error(f"Research Error: {e}")
            return "Prioritize tight spreads and limit trade frequency during high volatility."

    def analyze_performance(self):
        """Fetches current DB stats to see if we are in a drawdown or paying too much in fees."""
        session = self.Session()
        try:
            # Check last 100 trades for spread/commission impact
            trades = session.query(LiveTrade).order_by(LiveTrade.open_time.desc()).limit(100).all()
            # If no trades yet, return defaults
            if not trades:
                return {"drawdown": 0, "avg_profit": 0, "status": "STABLE"}
            
            # Simple heuristic analysis
            total_pnl = sum([t.pnl or 0 for t in trades])
            status = "STABLE"
            if total_pnl < -500: status = "DRAWDOWN_WARNING"
            
            return {"drawdown": total_pnl, "status": status}
        finally:
            session.close()

    def update_dynamic_rules(self):
        """Synthesizes research and analysis into the master JSON config."""
        research = self.research_hft_best_practices()
        performance = self.analyze_performance()
        
        prompt = f"""
        Based on the following Research and Performance data, update the Scalper Execution Rules.
        Research: {research}
        Current Performance: {performance}
        
        Output ONLY a valid JSON object with these keys: 
        "max_spread_pips" (float), 
        "risk_per_trade_percent" (float), 
        "max_concurrent_trades_per_pair" (int),
        "emergency_stop" (boolean)
        """
        
        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                response_format={ "type": "json_object" }
            )
            new_rules = json.loads(response.choices[0].message.content)
            
            with open(self.rules_file, "w") as f:
                json.dump(new_rules, f, indent=4)
                
            self.logger.info(f"Bot 5: Dynamic Rules Updated -> {new_rules}")
            self.log_activity(f"Decision Made: Spread limit set to {new_rules.get('max_spread_pips')}, Risk {new_rules.get('risk_per_trade_percent')}%")
        except Exception as e:
            self.logger.error(f"Decision Error: {e}")

    def run_analyst_loop(self):
        self.logger.info("Bot 5 AI Quant Strategist Started.")
        while True:
            self.update_dynamic_rules()
            # Every 4 hours research and re-adjust the whole portfolio strategy
            self.logger.info("Bot 5 sleeping for 4 hours...")
            time.sleep(4 * 3600)

if __name__ == "__main__":
    analyst = Bot5Analyst()
    analyst.run_analyst_loop()
