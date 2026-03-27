import os
import json
from flask import Flask, render_template, jsonify

app = Flask(__name__)

EXP_FILE = "backtest_experiments.json"

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/experiments")
def get_experiments():
    if not os.path.exists(EXP_FILE):
        return jsonify([])
    try:
        with open(EXP_FILE, 'r') as f:
            data = json.load(f)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)})

if __name__ == "__main__":
    # Standard Flask port 5000
    app.run(host="0.0.0.0", port=5000, debug=False)
