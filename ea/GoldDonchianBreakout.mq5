//+------------------------------------------------------------------+
//|                                       GoldDonchianBreakout.mq5    |
//|                                                                    |
//| Mechanical implementation of the ONE strategy validated in         |
//| reports/trading_plan.md and reports/validation_report.md:          |
//|                                                                     |
//|   Gold, 1-hour bars, 20-bar Donchian channel breakout.              |
//|   Stop  = 1.5 x ATR(14) at the signal bar                           |
//|   Target = 3.0 x ATR(14) at the signal bar (>=2:1 - see validation) |
//|   Max hold = 20 bars if neither SL nor TP is hit                    |
//|   One position at a time. Fixed-fractional risk sizing.             |
//|                                                                     |
//| IMPORTANT - read reports/trading_plan.md before using this for      |
//| real money. The underlying edge is NOT statistically proven         |
//| (95% CI includes zero, net expectancy +0.054R over 614 trades).     |
//| This EA automates EXECUTION of the tested rule; it does not make    |
//| the edge more real. Run it in the Strategy Tester first and         |
//| compare the results to reports/long_history_results.csv - they     |
//| should be in the same ballpark (not identical: your broker's tick   |
//| history, spread and slippage differ from the Yahoo Finance data     |
//| used for the Python backtest). Only after that, and only after      |
//| the demo/forward-test gate in trading_plan.md, consider live use.   |
//+------------------------------------------------------------------+
#property copyright "Educational / research use only. Not financial advice."
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>

//============================== INPUTS ==============================
input group "=== Entry/exit rule (do not change without re-validating in Python first) ==="
input int    InpDonchianPeriod    = 20;     // Donchian lookback, bars (excludes the signal bar itself)
input int    InpATRPeriod         = 14;     // ATR period for stop/target sizing
input double InpStopATRMult       = 1.5;    // Stop-loss distance = ATR * this
input double InpTargetATRMult     = 3.0;    // Take-profit distance = ATR * this
input int    InpMaxHoldBars       = 20;     // Force-close if neither SL nor TP hit within this many bars

input group "=== Risk management ==="
input double InpRiskPercent       = 0.5;    // % of account BALANCE risked per trade (trading_plan.md recommends 0.5)
input double InpMaxDrawdownR      = 10.0;   // Circuit breaker: halt new entries once cumulative R <= -this
input int    InpMagicNumber       = 20260914;
input bool   InpResetCircuitBreakerOnInit = false; // set true once + reload EA to clear a tripped breaker, then set back to false

input group "=== News filter (best-effort; needs your broker's MT5 calendar feed) ==="
input bool   InpUseNewsFilter     = true;   // skip new entries near high-impact USD releases
input int    InpNewsBufferMinutes = 60;     // +/- window around a high-impact USD event

input group "=== Logging ==="
input string InpLogFileName       = "GoldDonchianBreakout_TradeLog.csv"; // written under MQL5/Files

//============================== GLOBALS ==============================
CTrade   trade;
datetime g_lastBarTime = 0;
int      g_atrHandle   = INVALID_HANDLE;
string   g_gvCumR;
string   g_gvHalted;

//+------------------------------------------------------------------+
int OnInit()
{
   if(_Period != PERIOD_H1)
      Print("WARNING: this strategy was validated on H1 (1-hour) bars only. "
            "Current chart period is ", EnumToString((ENUM_TIMEFRAMES)_Period),
            ". Attach this EA to an H1 chart of your broker's gold symbol.");

   g_atrHandle = iATR(_Symbol, PERIOD_H1, InpATRPeriod);
   if(g_atrHandle == INVALID_HANDLE)
   {
      Print("Failed to create ATR indicator handle, error ", GetLastError());
      return INIT_FAILED;
   }

   g_gvCumR   = "FxTrading_" + _Symbol + "_" + IntegerToString(InpMagicNumber) + "_CumR";
   g_gvHalted = "FxTrading_" + _Symbol + "_" + IntegerToString(InpMagicNumber) + "_Halted";

   if(InpResetCircuitBreakerOnInit)
   {
      GlobalVariableSet(g_gvCumR, 0.0);
      GlobalVariableSet(g_gvHalted, 0.0);
      Print("Circuit breaker manually reset to 0. Set InpResetCircuitBreakerOnInit back to false now.");
   }
   else
   {
      if(!GlobalVariableCheck(g_gvCumR))   GlobalVariableSet(g_gvCumR, 0.0);
      if(!GlobalVariableCheck(g_gvHalted)) GlobalVariableSet(g_gvHalted, 0.0);
   }

   trade.SetExpertMagicNumber(InpMagicNumber);
   trade.SetTypeFillingBySymbol(_Symbol);

   InitLogFile();

   if(InpUseNewsFilter)
   {
      MqlCalendarValue probe[];
      int rc = CalendarValueHistory(probe, TimeCurrent() - 3600, TimeCurrent() + 3600, NULL, "USD");
      if(rc < 0)
         Print("WARNING: CalendarValueHistory returned an error (", GetLastError(),
               "). Your broker/terminal may not provide the MT5 economic calendar. "
               "If this warning persists, set InpUseNewsFilter=false - the EA will run without the news blackout.");
   }

   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   if(g_atrHandle != INVALID_HANDLE) IndicatorRelease(g_atrHandle);
   Comment("");
}

//+------------------------------------------------------------------+
//| Main loop - all decisions are made once per new H1 bar, matching  |
//| the "signal on bar close, act on next bar" logic of the backtest. |
//+------------------------------------------------------------------+
void OnTick()
{
   ManageOpenPositions(); // max-hold check - cheap, safe to run every tick

   if(!IsNewBar())
      return;

   TryEnter();
   UpdateChartComment();
}

bool IsNewBar()
{
   datetime t[];
   ArraySetAsSeries(t, true);
   if(CopyTime(_Symbol, PERIOD_H1, 0, 1, t) < 1) return false;
   if(t[0] != g_lastBarTime)
   {
      g_lastBarTime = t[0];
      return true;
   }
   return false;
}

//+------------------------------------------------------------------+
//| Donchian breakout signal, computed exactly like strategies.py:    |
//| donchian_breakout() in the Python repo. Series index 1 = the bar  |
//| that JUST closed (the "signal bar"); indices 2..N+1 = the N bars  |
//| strictly before it (the range being broken).                      |
//+------------------------------------------------------------------+
int CheckDonchianSignal(double &atrAtSignal)
{
   int need = InpDonchianPeriod + 3;

   double high[], low[], close[];
   ArraySetAsSeries(high, true);
   ArraySetAsSeries(low, true);
   ArraySetAsSeries(close, true);

   if(CopyHigh(_Symbol, PERIOD_H1, 0, need, high) < need)  return 0;
   if(CopyLow(_Symbol, PERIOD_H1, 0, need, low) < need)    return 0;
   if(CopyClose(_Symbol, PERIOD_H1, 0, need, close) < need) return 0;

   double atrBuf[];
   ArraySetAsSeries(atrBuf, true);
   if(CopyBuffer(g_atrHandle, 0, 0, 3, atrBuf) < 3) return 0;
   atrAtSignal = atrBuf[1]; // ATR at the signal bar (shift 1), same as Python's a.iloc[i]

   double highestPrior = high[2];
   double lowestPrior  = low[2];
   for(int i = 3; i <= InpDonchianPeriod + 1; i++)
   {
      if(high[i] > highestPrior) highestPrior = high[i];
      if(low[i]  < lowestPrior)  lowestPrior  = low[i];
   }

   double signalClose = close[1];

   if(signalClose > highestPrior) return 1;
   if(signalClose < lowestPrior)  return -1;
   return 0;
}

//+------------------------------------------------------------------+
bool HasOpenPosition()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0 || !PositionSelectByTicket(ticket)) continue;
      if(PositionGetString(POSITION_SYMBOL) == _Symbol && PositionGetInteger(POSITION_MAGIC) == InpMagicNumber)
         return true;
   }
   return false;
}

//+------------------------------------------------------------------+
//| Fixed-fractional position size from the stop distance, using the  |
//| symbol's own tick value/size so contract specs (oz per lot etc.)  |
//| don't need to be hard-coded.                                      |
//+------------------------------------------------------------------+
double CalcLotSize(double stopDistancePrice, double &riskMoneyOut)
{
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   riskMoneyOut = balance * (InpRiskPercent / 100.0);

   double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double tickSize  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tickSize <= 0 || tickValue <= 0 || stopDistancePrice <= 0)
      return 0;

   double moneyPerLotAtStop = (stopDistancePrice / tickSize) * tickValue;
   if(moneyPerLotAtStop <= 0) return 0;

   double lots = riskMoneyOut / moneyPerLotAtStop;

   double lotStep = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double lotMin  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double lotMax  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   if(lotStep <= 0) lotStep = 0.01;

   lots = MathFloor(lots / lotStep) * lotStep; // round DOWN - never risk more than the input %
   lots = MathMax(lotMin, MathMin(lotMax, lots));

   return lots;
}

//+------------------------------------------------------------------+
void TryEnter()
{
   if(GlobalVariableGet(g_gvHalted) != 0.0)
      return; // circuit breaker tripped - see README to review before resetting

   if(HasOpenPosition())
      return; // one position at a time

   if(InpUseNewsFilter && IsNearHighImpactUSDEvent(InpNewsBufferMinutes))
   {
      Print("News blackout window active - skipping entry check on this bar");
      return;
   }

   double atrAtSignal = 0;
   int signal = CheckDonchianSignal(atrAtSignal);
   if(signal == 0 || atrAtSignal <= 0)
      return;

   double stopDistance   = InpStopATRMult   * atrAtSignal;
   double targetDistance = InpTargetATRMult * atrAtSignal;

   double riskMoney = 0;
   double lots = CalcLotSize(stopDistance, riskMoney);
   if(lots <= 0)
   {
      Print("Calculated lot size is 0 (risk too small for this symbol's minimum lot / tick value). Skipping entry.");
      return;
   }

   MqlTick tick;
   if(!SymbolInfoTick(_Symbol, tick)) return;

   bool ok;
   if(signal == 1)
   {
      double sl = NormalizeDouble(tick.ask - stopDistance, _Digits);
      double tp = NormalizeDouble(tick.ask + targetDistance, _Digits);
      ok = trade.Buy(lots, _Symbol, 0.0, sl, tp, "GDB20");
   }
   else
   {
      double sl = NormalizeDouble(tick.bid + stopDistance, _Digits);
      double tp = NormalizeDouble(tick.bid - targetDistance, _Digits);
      ok = trade.Sell(lots, _Symbol, 0.0, sl, tp, "GDB20");
   }

   if(!ok)
   {
      Print("Order failed: ", trade.ResultRetcodeDescription());
      return;
   }

   if(PositionSelect(_Symbol))
   {
      ulong pt = PositionGetInteger(POSITION_TICKET);
      GlobalVariableSet("FxTrading_risk_"     + IntegerToString(pt), riskMoney);
      GlobalVariableSet("FxTrading_opentime_" + IntegerToString(pt), (double)TimeCurrent());
      PrintFormat("Entered %s lots=%.2f risk=%.2f stopDist=%.2f targetDist=%.2f",
                  (signal == 1 ? "LONG" : "SHORT"), lots, riskMoney, stopDistance, targetDistance);
   }
}

//+------------------------------------------------------------------+
//| Force-close any position held longer than InpMaxHoldBars bars.    |
//+------------------------------------------------------------------+
void ManageOpenPositions()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0 || !PositionSelectByTicket(ticket)) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol || PositionGetInteger(POSITION_MAGIC) != InpMagicNumber)
         continue;

      string key = "FxTrading_opentime_" + IntegerToString(ticket);
      if(!GlobalVariableCheck(key)) continue;

      datetime openTime = (datetime)GlobalVariableGet(key);
      int barsElapsed = (int)((TimeCurrent() - openTime) / PeriodSeconds(PERIOD_H1));
      if(barsElapsed >= InpMaxHoldBars)
      {
         PrintFormat("Max hold (%d bars) reached for ticket %I64u - closing at market", InpMaxHoldBars, ticket);
         trade.PositionClose(ticket);
      }
   }
}

//+------------------------------------------------------------------+
//| Logs every closed trade's R-multiple and updates/checks the       |
//| cumulative-R circuit breaker from trading_plan.md.                 |
//+------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction &trans, const MqlTradeRequest &request, const MqlTradeResult &result)
{
   if(trans.type != TRADE_TRANSACTION_DEAL_ADD) return;
   if(!HistoryDealSelect(trans.deal)) return;

   if(HistoryDealGetInteger(trans.deal, DEAL_MAGIC) != InpMagicNumber) return;
   if(HistoryDealGetString(trans.deal, DEAL_SYMBOL) != _Symbol) return;
   if((ENUM_DEAL_ENTRY)HistoryDealGetInteger(trans.deal, DEAL_ENTRY) != DEAL_ENTRY_OUT) return;

   ulong positionId = (ulong)HistoryDealGetInteger(trans.deal, DEAL_POSITION_ID);
   double profit = HistoryDealGetDouble(trans.deal, DEAL_PROFIT)
                 + HistoryDealGetDouble(trans.deal, DEAL_SWAP)
                 + HistoryDealGetDouble(trans.deal, DEAL_COMMISSION);

   string riskKey = "FxTrading_risk_"     + IntegerToString(positionId);
   string timeKey = "FxTrading_opentime_" + IntegerToString(positionId);

   double riskMoney = GlobalVariableCheck(riskKey) ? GlobalVariableGet(riskKey) : 0.0;
   double rMultiple = (riskMoney > 0) ? profit / riskMoney : 0.0;

   double cumR = GlobalVariableGet(g_gvCumR) + rMultiple;
   GlobalVariableSet(g_gvCumR, cumR);

   LogTrade(positionId, profit, rMultiple, cumR);

   if(GlobalVariableCheck(riskKey)) GlobalVariableDel(riskKey);
   if(GlobalVariableCheck(timeKey)) GlobalVariableDel(timeKey);

   if(cumR <= -MathAbs(InpMaxDrawdownR) && GlobalVariableGet(g_gvHalted) == 0.0)
   {
      GlobalVariableSet(g_gvHalted, 1.0);
      PrintFormat("*** CIRCUIT BREAKER TRIPPED *** cumulative R = %.2f <= -%.1f. New entries halted.", cumR, InpMaxDrawdownR);
      Alert(StringFormat("GoldDonchianBreakout: circuit breaker tripped at cumulative R=%.2f. Trading halted.", cumR));
   }
}

//+------------------------------------------------------------------+
void InitLogFile()
{
   if(!FileIsExist(InpLogFileName))
   {
      int h = FileOpen(InpLogFileName, FILE_WRITE | FILE_CSV | FILE_ANSI, ',');
      if(h != INVALID_HANDLE)
      {
         FileWrite(h, "close_time", "symbol", "position_id", "profit_money", "r_multiple", "cumulative_r", "balance");
         FileClose(h);
      }
      else
         Print("Failed to create log file, error ", GetLastError());
   }
}

void LogTrade(ulong positionId, double profit, double rMultiple, double cumR)
{
   int h = FileOpen(InpLogFileName, FILE_READ | FILE_WRITE | FILE_CSV | FILE_ANSI, ',');
   if(h == INVALID_HANDLE)
   {
      Print("Failed to open log file for append, error ", GetLastError());
      return;
   }
   FileSeek(h, 0, SEEK_END);
   FileWrite(h,
             TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS),
             _Symbol,
             (long)positionId,
             DoubleToString(profit, 2),
             DoubleToString(rMultiple, 3),
             DoubleToString(cumR, 3),
             DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 2));
   FileClose(h);
}

//+------------------------------------------------------------------+
//| Best-effort high-impact USD news filter using MT5's built-in      |
//| economic calendar. Not every broker/terminal build serves this -  |
//| OnInit() prints a warning if the calendar query errors out. If it |
//| does, set InpUseNewsFilter=false and rely on manual discipline    |
//| instead (see trading_plan.md).                                    |
//+------------------------------------------------------------------+
bool IsNearHighImpactUSDEvent(int bufferMinutes)
{
   datetime now  = TimeCurrent();
   datetime from = now - bufferMinutes * 60;
   datetime to   = now + bufferMinutes * 60;

   MqlCalendarValue values[];
   int n = CalendarValueHistory(values, from, to, NULL, "USD");
   if(n <= 0) return false;

   for(int i = 0; i < n; i++)
   {
      MqlCalendarEvent ev;
      if(!CalendarEventById(values[i].event_id, ev)) continue;
      if(ev.importance == CALENDAR_IMPORTANCE_HIGH)
         return true;
   }
   return false;
}

//+------------------------------------------------------------------+
void UpdateChartComment()
{
   double cumR   = GlobalVariableGet(g_gvCumR);
   bool   halted = GlobalVariableGet(g_gvHalted) != 0.0;

   Comment(StringFormat(
      "GoldDonchianBreakout (see reports/trading_plan.md)\n"
      "Status: %s\n"
      "Cumulative R: %.2f  (circuit breaker at -%.1f)\n"
      "Open position: %s\n"
      "Risk/trade: %.2f%%   Donchian(%d)  ATR(%d)  SL=%.1fx  TP=%.1fx  MaxHold=%d bars",
      halted ? "HALTED (circuit breaker tripped)" : "ACTIVE",
      cumR, InpMaxDrawdownR,
      HasOpenPosition() ? "YES" : "no",
      InpRiskPercent, InpDonchianPeriod, InpATRPeriod, InpStopATRMult, InpTargetATRMult, InpMaxHoldBars
   ));
}
//+------------------------------------------------------------------+
