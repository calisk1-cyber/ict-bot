import os
import json
import uuid
import requests
from base_agent import BaseAgent
from db_models import Strategy
from openai import OpenAI

class Bot2Hunter(BaseAgent):
    def __init__(self):
        super().__init__("Bot2-Hunter")
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.github_token = os.getenv("GITHUB_TOKEN")

    def search_github(self, query: str):
        """Searches GitHub for potential trading strategies."""
        self.logger.info(f"Searching GitHub for: {query}")
        url = f"https://api.github.com/search/repositories?q={query}&sort=stars&order=desc"
        headers = {"Authorization": f"token {self.github_token}"} if self.github_token else {}
        
        try:
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                items = response.json().get("items", [])[:5]
                return [item['html_url'] for item in items]
        except Exception as e:
            self.logger.error(f"GitHub Search Error: {e}")
        return []

    def extract_logic_with_llm(self, source_content: str):
        """Uses GPT-4o to extract structured strategy logic from raw text/code."""
        self.logger.info("Extracting logic using LLM...")
        prompt = f"""
        Extract a forex trading strategy from the following content.
        Output MUST be in JSON format matching this schema:
        {{
          "name": "string",
          "type": "trend_following | mean_reversion | breakout | ml_based | hybrid",
          "timeframes": ["M1", "M15", "H1", "H4", "D1"],
          "pairs": ["EUR_USD", "GBP_USD"],
          "entry_logic": "string description",
          "exit_logic": "string description",
          "indicators": ["list of indicators"],
          "confidence_score": 0.0-1.0
        }}
        
        Content:
        {source_content[:4000]}
        """
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "system", "content": "You are a specialized trading strategy analyst."},
                          {"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            self.logger.error(f"LLM Extraction Error: {e}")
            return None

    def find_new_strategies(self):
        """Main loop for finding new strategies."""
        queries = [
            "forex strategy python ICT", "EURUSD algorithmic trading", "mean reversion eurusd",
            "price action trading python", "harmonic patterns bot", "supply and demand forex",
            "order flow trading logic", "trailing stop strategy python"
        ]
        
        for query in queries:
            urls = self.search_github(query)
            for url in urls:
                if self.is_processed("github_repos", url):
                    self.logger.debug(f"Skipping already processed repo: {url}")
                    continue
                
                # In a real scenario, we would scrape the README or code content
                # For this implementation, we simulate a found strategy based on the URL context
                mock_content = f"Found a repository at {url} focused on {query}."
                strat_json = self.extract_logic_with_llm(mock_content)
                
                if strat_json and strat_json.get("confidence_score", 0) > 0.5:
                    self.mark_as_processed("github_repos", url)
                    strat_id = str(uuid.uuid4())
                    strat_json["strategy_id"] = strat_id
                    strat_json["source_url"] = url
                    
                    # Save to DB
                    session = self.Session()
                    try:
                        new_strat = Strategy(
                            id=strat_id,
                            name=strat_json['name'],
                            type=strat_json['type'],
                            timeframes=strat_json.get('timeframes'),
                            pairs=strat_json.get('pairs'),
                            entry_logic=strat_json['entry_logic'],
                            exit_logic=strat_json['exit_logic'],
                            indicators=strat_json.get('indicators'),
                            confidence_score=strat_json['confidence_score'],
                            source_url=url
                        )
                        session.add(new_strat)
                        session.commit()
                        self.logger.info(f"Strategy {strat_json['name']} saved to DB.")
                        self.log_activity(f"Successfully added strategy: {strat_json['name']}")
                        
                        # Push to Backtest Queue
                        self.push_to_queue("strategies:pending", strat_json)
                    except Exception as e:
                        self.logger.error(f"DB Error: {e}")
                        session.rollback()
                    finally:
                        session.close()

if __name__ == "__main__":
    import time
    hunter = Bot2Hunter()
    while True:
        try:
            hunter.log_activity("Searching for NEW strategies")
            hunter.find_new_strategies()
        except Exception as e:
            hunter.log_activity(f"CRITICAL ERROR: {str(e)}")
            hunter.logger.error(f"Hunter Loop Error: {e}")
        
        hunter.log_activity("Sleeping for 10 minutes")
        hunter.logger.info("Bot 2 Hunter sleeping for 10 minutes...")
        time.sleep(600) # Reduced from 3600
