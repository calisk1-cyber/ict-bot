import os
import json
import time
from base_agent import BaseAgent
from db_models import LiveTrade, Strategy
from openai import OpenAI
from v20 import Context
import v20.order
import uuid

class Bot4Trader(BaseAgent):
    def __init__(self):
        super().__init__("Bot4-Trader")
        self.openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.oanda_token = os.getenv("OANDA_API_KEY")
        self.oanda_account_id = os.getenv("OANDA_ACCOUNT_ID")
        self.oanda_env = os.getenv("OANDA_ENV", "practice")
        
        self.ctx = Context(
            "api-fxpractice.oanda.com" if self.oanda_env == "practice" else "api-fxtrade.oanda.com",
            443,
            True,
            application="Bot4",
            token=self.oanda_token
        )
        self.active_strategy = None
        self.log_file = "live_trade_log.txt"

    def check_news_filter(self):
        self.logger.info("News filter: CLEAR (No high impact news).")
        return True

    def get_current_spread(self, pair: str):
        """Fetches the bid/ask spread from OANDA."""
        try:
            response = self.ctx.pricing.get(self.oanda_account_id, instruments=pair)
            price = response.get("prices", 200)[0]
            spread = abs(float(price.closeoutAsk) - float(price.closeoutBid))
            
            # Pip conversion
            if "JPY" in pair: spread_pips = spread * 100
            elif "XAU" in pair: spread_pips = spread # Gold is absolute
            else: spread_pips = spread * 10000
            
            return round(spread_pips, 2)
        except Exception as e:
            self.logger.error(f"Spread Fetch Error: {e}")
            return 99.0 # High fallback to prevent trading
            
    def get_gpt_confirmation(self, signal_info: dict):
        prompt = f"""
        Active Strategy: {signal_info.get('strategy_name')}
        Current Market Snapshot: {signal_info.get('price_data')}
        Indicators: {signal_info.get('indicators')}
        Signal: {signal_info.get('action')} @ {signal_info.get('price')}
        
        Should I execute this trade?
        Answer ONLY in JSON format: {{"action": "execute"|"wait", "confidence": 0.0-1.0, "reason": "string"}}
        """
        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a professional risk manager."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"}
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            self.logger.error(f"GPT Confirmation Error: {e}")
            return {"action": "wait", "confidence": 0, "reason": f"Error: {e}"}

    def _write_log(self, line: str):
        """Log dosyasına thread-safe yazar."""
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def execute_trade(self, pair: str, direction: str, price: float, sl: float, tp: float, reasoning: str):
        self.logger.info(f"EXECUTING {direction} on {pair} @ {price}")

        units    = 1000 if direction == "BUY" else -1000
        lot_size = abs(units) / 100000

        # Pip büyüklüğü (JPY ve egzotikler için 0.01, diğerleri 0.0001)
        if "JPY" in pair:
            pip_size = 0.01
        elif "XAU" in pair or "NAS" in pair or "US30" in pair or "DE40" in pair:
            pip_size = 1.0
        else:
            pip_size = 0.0001

        sl_pips = round(abs(price - sl) / pip_size, 1)
        tp_pips = round(abs(price - tp) / pip_size, 1)

        order_req = v20.order.MarketOrderRequest(
            instrument=pair,
            units=units,
            stopLossOnFill=v20.transaction.StopLossDetails(price=str(round(sl, 5))),
            takeProfitOnFill=v20.transaction.TakeProfitDetails(price=str(round(tp, 5)))
        )

        try:
            response = self.ctx.order.market(self.oanda_account_id, order=order_req)

            if response.status == 201:
                # OANDA'dan dönen gerçek Trade ID'yi al (v20 nesne tabanlı erişim)
                oanda_data = response.get("orderFillTransaction", 201)
                trade_opened = getattr(oanda_data, "tradeOpened", None)
                trade_id = str(getattr(trade_opened, "tradeID", None)) if trade_opened else None
                
                if not trade_id or trade_id == "None":
                    # Eğer doğrudan trade açılmadıysa alternatif ID
                    trade_id = str(getattr(oanda_data, "id", uuid.uuid4()))

                open_time = time.strftime('%Y-%m-%d %H:%M:%S+00:00')

                # ✅ Açılış logu — audit için tam format
                log_line = (
                    f"{open_time} | {pair} | {direction} | "
                    f"Entry:{price:.5f} | SL:{sl:.5f} | TP:{tp:.5f} | "
                    f"Lot:{lot_size:.4f} | SLpips:{sl_pips} | TPpips:{tp_pips} | "
                    f"PnL:0.00 | OPEN | ID:{trade_id}"
                )
                self._write_log(log_line)

                # DB kaydı
                session = self.Session()
                new_trade = LiveTrade(
                    trade_id=trade_id,
                    pair=pair,
                    direction=direction,
                    open_price=price,
                    sl=sl,
                    tp=tp,
                    lot_size=lot_size,
                    sl_pips=sl_pips,
                    status="OPEN",
                    strategy_id=self.active_strategy.get("active_strategy_id") if self.active_strategy else "unknown",
                    gpt_reasoning=reasoning
                )
                session.add(new_trade)
                session.commit()
                session.close()
                self.logger.info(f"Trade açıldı. ID: {trade_id} | {pair} {direction} | SL:{sl_pips}pip | TP:{tp_pips}pip")
            else:
                self.logger.error(f"OANDA Emir Hatası: {response.body}")

        except Exception as e:
            self.logger.error(f"Execution Error: {e}")

    def check_and_close_trades(self):
        """Her döngüde açık pozisyonları OANDA'dan kontrol eder, kapananları loglar."""
        try:
            session = self.Session()
            open_trades = session.query(LiveTrade).filter_by(status="OPEN").all()

            for trade in open_trades:
                try:
                    response = self.ctx.trade.get(self.oanda_account_id, trade.trade_id)

                    if response.status != 200:
                        continue

                    oanda_trade = response.get("trade", 200)
                    state = getattr(oanda_trade, "state", "OPEN")

                    if state == "CLOSED":
                        realized_pnl = float(getattr(oanda_trade, "realizedPL", 0))
                        # Kapanış fiyatı için son işlemi kontrol et
                        close_price  = float(getattr(oanda_trade, "averageClosePrice", 0))
                        close_time   = getattr(oanda_trade, "closeTime", time.strftime('%Y-%m-%d %H:%M:%S+00:00'))
                        outcome      = "TP" if realized_pnl > 0 else "SL"

                        # ✅ Kapanış logu — gerçek PnL ile
                        log_line = (
                            f"{close_time} | {trade.pair} | {trade.direction} | "
                            f"Entry:{trade.open_price:.5f} | SL:{trade.sl:.5f} | TP:{trade.tp:.5f} | "
                            f"Close:{close_price:.5f} | "
                            f"Lot:{trade.lot_size:.4f} | SLpips:{trade.sl_pips} | "
                            f"PnL:{realized_pnl:.2f} | {outcome} | ID:{trade.trade_id}"
                        )
                        self._write_log(log_line)

                        # DB güncelle
                        trade.status      = "CLOSED"
                        trade.close_price = close_price
                        trade.pnl         = realized_pnl
                        trade.outcome     = outcome
                        session.commit()

                        self.logger.info(
                            f"Trade kapandı: {trade.pair} | "
                            f"PnL: {realized_pnl:.2f} | {outcome} | ID: {trade.trade_id}"
                        )

                except Exception as e:
                    self.logger.error(f"Trade kontrol hatası (ID:{trade.trade_id}): {e}")
                    continue

            session.close()

        except Exception as e:
            self.logger.error(f"check_and_close_trades Error: {e}")

    def run_trading_loop(self):
        self.logger.info("Bot 4 Trader canlı döngüsü başlıyor...")
        while True:
            print(f"--- LOOP START: {time.strftime('%H:%M:%S')} ---", flush=True)
            try:
                # 1. Kapanan pozisyonları kontrol et ve logla
                print("DEBUG: check_and_close_trades basliyor...", flush=True)
                self.check_and_close_trades()
                print("DEBUG: check_and_close_trades bitti.", flush=True)

                # 2. Aktif stratejiyi güncelle
                new_strat = self.pull_from_queue("strategy:active", timeout=1)
                if new_strat:
                    self.active_strategy = new_strat
                    self.logger.info(f"Strateji güncellendi: {new_strat['active_strategy_id']}")
                    print(f"DEBUG: Strateji güncellendi: {new_strat['active_strategy_id']}")

                if not self.active_strategy:
                    self.update_status("Idle: Aktif strateji yok")
                    print("DEBUG: Idle: Aktif strateji yok...")
                    time.sleep(10)
                    continue

                strat_id = self.active_strategy.get("active_strategy_id")
                print(f"DEBUG: Piyasa izleniyor: {strat_id} | Pair: EUR_USD")
                self.log_activity(f"Piyasa izleniyor: {strat_id}")

                # 3. Sinyal üretimi (şu an simülasyon)
                if self.check_news_filter():
                    signal = {
                        "strategy_name": "Active ICT Scalp",
                        "price_data":    "EUR_USD @ 1.0850",
                        "indicators":    "FVG Bull detected, OB support",
                        "action":        "BUY",
                        "price":         1.0850
                    }

                    signal_key = f"{strat_id}:{signal['action']}:{signal['price']}"
                    if self.is_processed("executed_signals", signal_key):
                        self.logger.debug(f"Sinyal zaten işlendi: {signal_key}")
                        time.sleep(60)
                        continue

                    confirmation = self.get_gpt_confirmation(signal)
                    
                    confirmation = self.get_gpt_confirmation(signal)
                    if confirmation.get("action") == "execute" and confirmation.get("confidence", 0) > 0.75:
                        self.execute_trade(
                            pair=      "EUR_USD",
                            direction= "BUY",
                            price=     1.0850,
                            sl=        1.0830,
                            tp=        1.0900,
                            reasoning= str(confirmation.get("reason", ""))
                        )
                        self.mark_as_processed("executed_signals", signal_key)

                time.sleep(60)

            except KeyboardInterrupt:
                self.logger.info("Bot durduruldu.")
                break
            except Exception as e:
                self.logger.error(f"Trading Loop Error: {e}")
                time.sleep(10)

if __name__ == "__main__":
    trader = Bot4Trader()
    trader.run_trading_loop()
