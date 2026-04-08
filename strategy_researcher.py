import os
import json
import subprocess
import sys
from openai import OpenAI
from datetime import datetime
from dotenv import load_dotenv

# --- CONFIG ---
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
STAGING_FILE = "ict_utils_experimental.py"
PROD_FILE = "ict_utils.py"
EXPERIMENT_LOG = "strategy_experiments.json"

def generate_new_strategy_hypothesis():
    """Uses AI to brainstorm a new ICT/SMC technical indicator logic."""
    print("--- [RESEARCHER] Brainstorming New Strategy Component ---")
    
    prompt = """
    You are an expert ICT/SMC (Institutional Capital Trading) quant researcher.
    Current indicators: FVG, Turtle Soup, IFVG, MSS, AMD.
    Task: Propose a NEW technical indicator logic in Python based on ICT concepts.
    Include necessary imports (pandas as pd, numpy as np, pandas_ta as ta).
    Return ONLY raw python code. No markdown backticks.
    Function must be: `find_new_logic(df)` which adds 'SIGNAL_NEW' (bool) column.
    """
    
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": "You are a Python code generator. Output ONLY raw code without markdown formatting."},
                  {"role": "user", "content": prompt}]
    )
    code = response.choices[0].message.content
    code = code.replace("```python", "").replace("```", "").strip()
    return code

def run_staging_validation():
    """Runs backtest with experimental logic."""
    print("--- [STAGING] Running 100-Trade Validation ---")
    env = {**os.environ, "STAGING": "1"}
    result = subprocess.run([sys.executable, "realistic_backtest_v8.py"], env=env, capture_output=True, text=True)
    try:
        # Extract the metrics JSON from stdout
        output = result.stdout.split("="*50)[-1]
        metrics = json.loads(output)
        return metrics
    except Exception as e:
        print(f"Staging Error: {e}")
        return None

def main_research_loop():
    print("--- [SINGULARITY] AUTONOMOUS RESEARCHER STARTED ---")
    
    for cycle in range(1, 4): # Try 3 cycles
        print(f"--- [CYCLE {cycle}] ---")
        hypothesis_code = generate_new_strategy_hypothesis()
        
        with open(STAGING_FILE, "w") as f:
            f.write(hypothesis_code)
            
        metrics = run_staging_validation()
        if metrics and metrics.get("performance", {}).get("net_pnl", 0) > 150:
            pnl = metrics['performance']['net_pnl']
            print(f"[SUCCESS] Strategy Found! PnL: {pnl}")
            
            # --- PROMO ENGINE ---
            print("--- [PROMOTION] Merging Experimental Logic to Production ---")
            with open(PROD_FILE, "a") as f:
                f.write("\n\n# --- AI EVOLVED LOGIC (PROMOTED) ---\n")
                f.write(hypothesis_code)
            
            # Update weights for the new component
            weights_file = "optimized_weights.json"
            if os.path.exists(weights_file):
                with open(weights_file, "r") as f:
                    w = json.load(f)
                w["SIGNAL_NEW"] = 25 # Initial weight for new logic
                with open(weights_file, "w") as f:
                    json.dump(w, f, indent=4)
            break
        else:
            print("[REJECTED] Performance threshold not met.")

if __name__ == "__main__":
    main_research_loop()
