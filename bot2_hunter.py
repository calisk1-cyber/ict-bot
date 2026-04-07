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

    def auto_debug_code(self, python_code: str):
        """Dry-runs Python code to check for syntax errors using AST."""
        try:
            import ast
            ast.parse(python_code)
            return True, "Syntax OK"
        except SyntaxError as e:
            return False, f"Syntax Error: {str(e)}"
            
    def search_arxiv(self):
        """Scrapes Cornell ArXiv for latest Quantitative Finance papers."""
        self.logger.info("Searching ArXiv for new Q-Fin papers...")
        import urllib.request
        import xml.etree.ElementTree as ET
        url = "http://export.arxiv.org/api/query?search_query=cat:q-fin.TR&sortBy=submittedDate&sortOrder=desc&max_results=3"
        papers = []
        try:
            response = urllib.request.urlopen(url)
            xml_data = response.read()
            root = ET.fromstring(xml_data)
            for entry in root.findall('{http://www.w3.org/2005/Atom}entry'):
                t_node = entry.find('{http://www.w3.org/2005/Atom}title')
                s_node = entry.find('{http://www.w3.org/2005/Atom}summary')
                l_node = entry.find('{http://www.w3.org/2005/Atom}id')
                title = t_node.text if t_node is not None else "No Title"
                summary = s_node.text if s_node is not None else "No Summary"
                link = l_node.text if l_node is not None else "No Link"
                papers.append({'title': title, 'summary': summary, 'link': link})
            return papers
        except Exception as e:
            self.logger.error(f"ArXiv Error: {e}")
            return []

    def extract_logic_with_llm(self, source_content: str, source_type: str = "general"):
        """Uses GPT-4o to extract and convert logic from PineScript, MQL5, ArXiv, or Github into Standard Python."""
        self.logger.info(f"Extracting logic using LLM for type: {source_type}...")
        
        context_prompt = ""
        if source_type == "pinescript":
            context_prompt = "The following is TradingView PineScript code. Convert its trading logic into standard Python rules."
        elif source_type == "mql5":
            context_prompt = "The following is MetaTrader MQL4/MQL5 code. Understand the EA logic and extract the rules into standard Python logic."
        elif source_type == "arxiv":
            context_prompt = "The following is an abstract from a Quantitative Finance paper. Extract the mathematical trading strategy into Python logic rules."
        else:
            context_prompt = "Extract a forex trading strategy from the following github content."

        prompt = f"""
        {context_prompt}
        Output MUST be in JSON format matching this exact schema:
        {{
          "name": "string",
          "type": "trend_following | mean_reversion | breakout | ml_based | hybrid",
          "timeframes": ["M1", "M15", "H1", "H4", "D1"],
          "pairs": ["EUR_USD", "GBP_USD"],
          "entry_logic": "string (Valid Python code snippet or clear pseudocode)",
          "exit_logic": "string (Valid Python code snippet or clear pseudocode)",
          "indicators": ["list of indicators"],
          "confidence_score": 0.0-1.0
        }}
        
        Content:
        {source_content[:4000]}
        """
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "system", "content": "You are a specialized Quant Developer translating trading logic into Python."},
                          {"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            data = json.loads(response.choices[0].message.content)
            
            # --- AST AUTO-DEBUG SANDBOX ---
            entry_code = data.get("entry_logic", "")
            if entry_code and "if " in entry_code: 
                is_valid, msg = self.auto_debug_code(entry_code)
                if not is_valid:
                    self.logger.warning(f"AST Sandbox failed for extracted code: {msg}. Retrying is needed in future versions.")
                    data["confidence_score"] -= 0.2 # Penalize bad syntax
            
            return data
        except Exception as e:
            self.logger.error(f"LLM Extraction Error: {e}")
            return None

    def find_new_strategies(self):
        """Main loop for finding new strategies through Multi-Source Hunting (Github, ArXiv, TradingView, MQL)."""
        # 1. GITHUB HUNTING
        github_queries = ["PineScript trading strategy", "MQL5 EA expert advisor", "forex order flow python"]
        for query in github_queries:
            urls = self.search_github(query)
            for url in urls:
                if self.is_processed("github_repos", url): continue
                # We determine type by query to feed different context
                stype = "pinescript" if "PineScript" in query else "mql5" if "MQL5" in query else "github"
                mock_content = f"Scraped code from {url} focusing on {query}." # Placeholder for real scraping
                strat_json = self.extract_logic_with_llm(mock_content, source_type=stype)
                self._save_and_push_strategy(strat_json, url, "github_repos")

        # 2. ARXIV HUNTING
        arxiv_papers = self.search_arxiv()
        for paper in arxiv_papers:
            if self.is_processed("arxiv_papers", paper['link']): continue
            content = f"Title: {paper['title']}\nAbstract: {paper['summary']}"
            strat_json = self.extract_logic_with_llm(content, source_type="arxiv")
            self._save_and_push_strategy(strat_json, paper['link'], "arxiv_papers")

    def _save_and_push_strategy(self, strat_json, source_link, category_key):
        if not strat_json or strat_json.get("confidence_score", 0) <= 0.5:
            self.mark_as_processed(category_key, source_link)
            return
            
        self.mark_as_processed(category_key, source_link)
        strat_id = str(uuid.uuid4())
        strat_json["strategy_id"] = strat_id
        strat_json["source_url"] = source_link
        
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
                source_url=source_link
            )
            session.add(new_strat)
            session.commit()
            self.logger.info(f"Strategy {strat_json['name']} saved to DB from {category_key}.")
            self.log_activity(f"New V2.0 Strategy: {strat_json['name']}")
            self.push_to_queue("strategies:pending", strat_json)
        except Exception as e:
            self.logger.error(f"DB Error while saving strategy: {e}")
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
