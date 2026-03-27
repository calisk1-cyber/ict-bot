import os
import json
import subprocess
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def evolve_logic():
    print("--- STARTING LOGIC EVOLUTION CYCLE ---")
    
    knowledge_file = "ict_knowledge_base.json"
    utils_file = "ict_utils_experimental.py"
    
    if not os.path.exists(knowledge_file) or not os.path.exists(utils_file):
        print("Missing files for evolution.")
        return

    with open(knowledge_file, 'r') as f:
        kb = json.load(f)
        
    with open(utils_file, 'r') as f:
        current_code = f.read()
        
    findings = kb.get("latest_r_and_d", [])
    if not findings:
        print("No new R&D findings to implement.")
        return

    # Prompt AI to suggest specific code improvements or additions
    prompt = f"""
    You are an Expert Python Developer and ICT Strategist.
    Current ict_utils.py code is provided.
    Latest R&D findings: {findings}
    
    TASK: Pick ONE finding that is not yet fully implemented and provide a Python function to add to ict_utils.py.
    Ensure the function follows the existing style (Pandas/Numpy/pandas-ta).
    
    Respond ONLY with the Python code for the new function. No explanation.
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}]
        )
        new_code_snippet = response.choices[0].message.content.strip()
        # Clean up Markdown backticks if present
        if "```python" in new_code_snippet:
            new_code_snippet = new_code_snippet.split("```python")[1].split("```")[0].strip()
        elif "```" in new_code_snippet:
            new_code_snippet = new_code_snippet.split("```")[1].split("```")[0].strip()

        # APPEND the new code to ict_utils.py
        with open(utils_file, 'a') as f:
            f.write(f"\n\n# --- EVOLVED LOGIC (Autonomous R&D) ---\n{new_code_snippet}\n")
            
        print(f"Successfully implemented new logic into {utils_file}")
        
    except Exception as e:
        print(f"Evolution Error: {e}")

if __name__ == "__main__":
    evolve_logic()
