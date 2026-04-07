import os
import json
from sqlalchemy import create_engine, MetaData, Table, select
from sqlalchemy.orm import sessionmaker

# DB Setup
db_url = os.getenv("DATABASE_URL", "postgresql://postgres:%40%40y%C4%B1ld%C4%B1z@localhost:5432/postgres")
engine = create_engine(db_url)
Session = sessionmaker(bind=engine)
metadata = MetaData()

def get_report():
    try:
        session = Session()
        
        # Load tables
        strategies = Table('strategies', metadata, autoload_with=engine)
        backtests = Table('backtest_results', metadata, autoload_with=engine)
        
        # 1. Total Strategies Found
        n_strats = session.query(strategies).count()
        
        # 2. Total Backtests Completed
        n_backtests = session.query(backtests).count()
        
        # 3. Latest 3 Backtests
        latest_bt_query = select(backtests).order_by(backtests.c.backtested_at.desc()).limit(3)
        latest_bts = session.execute(latest_bt_query).fetchall()
        
        # 4. Success Rate (Passed vs Total)
        passed_count = session.query(backtests).filter(backtests.c.passed == True).count()
        
        report = {
            "total_strategies_found": n_strats,
            "total_backtests_completed": n_backtests,
            "passed_backtests": passed_count,
            "latest_results": [dict(row._mapping) for row in latest_bts]
        }
        
        print(json.dumps(report, indent=2, default=str))
        session.close()
    except Exception as e:
        print(f"Error generating report: {e}")

if __name__ == "__main__":
    get_report()
