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
        self.report_path = "/root/bot/analyst_insights.md"
        if not os.path.exists("/root/bot"): os.makedirs("/root/bot") 
        
        # Local fallback
        if not os.path.exists(os.path.dirname(self.report_path)):
            self.report_path = "analyst_insights.md"

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

    def generate_daily_insight_report(self):
        """Synthesizes research and activity into a user-friendly report."""
        research = self.research_hft_best_practices()
        performance = self.analyze_performance()
        
        prompt = f"""
        Act as an Elite Quant Consultant. Generate a daily 'Trading System Improvement Report' based on this data:
        Research Findings: {research}
        Recent Performance: {performance}
        
        The report should be in professional Markdown. It should include:
        1. 'Analiz & Özet' (Analysis of current state)
        2. 'Yeni Keşfedilen Strateji İpuçları' (Tips from research)
        3. 'Geliştirme Tavsiyeleri' (Actionable suggestions for the user to improve the bot)
        4. 'Risk Notları' (Warning/Note on current risk)
        
        Write the report in TURKISH.
        """
        
        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}]
            )
            report_content = response.choices[0].message.content
            
            with open(self.report_path, "w", encoding="utf-8") as f:
                f.write(f"# 🏛️ BOT 5 ANALYST RAPORU - {datetime.now().strftime('%Y-%m-%d')}\n\n")
                f.write(report_content)
                
            self.logger.info(f"Bot 5: Daily Report Generated at {self.report_path}")
            self.log_activity("Daily Insight Report Generated.")
        except Exception as e:
            self.logger.error(f"Report Generation Error: {e}")

    def run_analyst_loop(self):
        self.logger.info("Bot 5 Research Consultant Started.")
        while True:
            # Generate insights for the user to read
            self.generate_daily_insight_report()
            # Research every 6 hours
            self.logger.info("Bot 5 Consultant sleeping for 6 hours...")
            time.sleep(6 * 3600)

if __name__ == "__main__":
    analyst = Bot5Analyst()
    analyst.run_analyst_loop()
