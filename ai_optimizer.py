import pandas as pd
import os
from openai import OpenAI
from datetime import datetime
import sys
import json
from dotenv import load_dotenv

load_dotenv()

# Config
LIVE_LOG = "ict_trade_history.csv"
BT_LOG = "backtest_history.csv"
KNOWLEDGE_FILE = "ict_knowledge_base.json"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

def run_daily_optimization(mode="live"):
    log_file = BT_LOG if mode == "backtest" else LIVE_LOG
    print(f"AI Strategy Audit ({mode.upper()}) Starting... Data Source: {log_file}")
    
    if not os.path.exists(log_file):
        print(f"Error: {log_file} not found.")
        return

    try:
        df_history = pd.read_csv(log_file).tail(50)
        kb_data = {}
        if os.path.exists(KNOWLEDGE_FILE):
            with open(KNOWLEDGE_FILE, 'r') as f:
                kb_data = json.load(f)

        prompt = f"""
        Analyze these ICT trades ({mode}) and optimize STRATEGY_WEIGHTS.
        Trade History: {df_history.to_json()}
        Technical Knowledge: {json.dumps(kb_data)}
        
        Provide a JSON block with 'fvg', 'turtle_soup', 'ifvg', 'sb', 'macro' weights (total ~100-110).
        Also provide a short analysis in Markdown.
        """
        
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": "You are an ICT Institutional Trader."},
                      {"role": "user", "content": prompt}]
        )
        
        analysis = response.choices[0].message.content
        
        # Extract and save weights
        import re
        json_match = re.search(r'\{.*\}', analysis, re.DOTALL)
        if json_match:
            new_weights = json.loads(json_match.group())
            # Flatten if nested
            if "strategy_weights" in new_weights:
                new_weights = new_weights["strategy_weights"]
                
            with open("optimized_weights.json", "w") as f:
                json.dump(new_weights, f, indent=4)
            print("Successfully updated optimized_weights.json")

        report_file = "ict_strategy_report.md"
        with open(report_file, "w", encoding="utf-8") as f:
            f.write(f"# ICT Strategy Audit - {datetime.now().strftime('%Y-%m-%d')}\n\n")
            f.write(analysis)
        print(f"Report created: {report_file}")

        # EXPERIMENT DATABASE LOGGING (For Dashboard)
        exp_file = "backtest_experiments.json"
        experiments = []
        if os.path.exists(exp_file):
            with open(exp_file, 'r') as f:
                experiments = json.load(f)
        
        # Calculate approximate performance from history if possible
        performance = {"return": 0.0, "win_rate": 0.0}
        if not df_history.empty and 'Gain' in df_history.columns:
            performance["return"] = round(df_history['Gain'].sum(), 2)
            performance["win_rate"] = round((df_history['Gain'] > 0).mean() * 100, 1)

        new_entry = {
            "timestamp": datetime.now().isoformat(),
            "mode": mode,
            "performance": performance,
            "weights": new_weights if 'new_weights' in locals() else {},
            "analysis": analysis,
            "knowledge": kb_data.get("latest_r_and_d", [])
        }
        experiments.append(new_entry)
        with open(exp_file, 'w') as f:
            json.dump(experiments, f, indent=4)
        print("Logged experiment to dashboard database.")
        
    except Exception as e:
        print(f"AI Optimization Error: {e}")

if __name__ == "__main__":
    mode = "live"
    if len(sys.argv) > 1 and sys.argv[1] == "--backtest":
        mode = "backtest"
    run_daily_optimization(mode=mode)
