from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, JSON, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class Strategy(Base):
    __tablename__ = 'strategies'
    id = Column(String, primary_key=True) # UUID
    name = Column(String)
    type = Column(String)
    timeframes = Column(JSON)
    pairs = Column(JSON)
    entry_logic = Column(String)
    exit_logic = Column(String)
    indicators = Column(JSON)
    confidence_score = Column(Float)
    source_url = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

class BacktestResult(Base):
    __tablename__ = 'backtest_results'
    id = Column(Integer, primary_key=True)
    strategy_id = Column(String, ForeignKey('strategies.id'))
    total_return = Column(Float)
    sharpe_ratio = Column(Float)
    max_drawdown = Column(Float)
    win_rate = Column(Float)
    profit_factor = Column(Float)
    total_trades = Column(Integer)
    passed = Column(Boolean)
    fail_reason = Column(String)
    backtested_at = Column(DateTime, default=datetime.utcnow)

class LiveTrade(Base):
    __tablename__ = 'live_trades'
    trade_id = Column(String, primary_key=True)
    pair = Column(String)
    direction = Column(String) # BUY/SELL
    open_price = Column(Float)
    close_price = Column(Float, nullable=True)
    sl = Column(Float)
    tp = Column(Float)
    pnl = Column(Float, nullable=True)
    strategy_id = Column(String, ForeignKey('strategies.id'))
    lot_size = Column(Float, default=0.01)
    sl_pips = Column(Float, default=0.0)
    status = Column(String, default='OPEN') # OPEN/CLOSED
    outcome = Column(String, nullable=True) # TP/SL
    gpt_reasoning = Column(String)
    open_time = Column(DateTime, default=datetime.utcnow)
    close_time = Column(DateTime, nullable=True)

def init_db(engine):
    Base.metadata.create_all(engine)
