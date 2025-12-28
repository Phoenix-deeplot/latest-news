# auction_screener.py
# Requires: pip install tushare pandas requests tqdm
import tushare as ts
import pandas as pd
import numpy as np
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

# -------------------------- Utility / helpers --------------------------
def ts_to_gm(ts_code: str) -> str:
    """
    Convert tushare ts_code like '000001.SZ' -> 'SZSE.000001'
    """
    parts = ts_code.split('.')
    if len(parts) != 2:
        return ts_code
    code, exch = parts[0], parts[1].upper()
    exch_map = {'SZ': 'SZSE', 'SH': 'SHSE'}
    return f"{exch_map.get(exch, exch)}.{code}"

def safe_float(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default

# -------------------------- 1) TuShare-based full-market auction screener (recommended) --------------------------
def get_auction_candidates_tushare(trade_date: str,
                                   tushare_token: str,
                                   gap_threshold: float = 0.07,
                                   vol_multiplier_threshold: float = 3.0,
                                   max_pullback: float = 0.05,
                                   workers: int = 8,
                                   sleep_per_call: float = 0.12):
    """
    Use TuShare Pro's auction API (stk_auction_o / stk_auction) to fetch open-auction data
    and filter whole market by gap >= gap_threshold and volume multiplier >= vol_multiplier_threshold.

    Args:
      trade_date: 'YYYYMMDD' string
      tushare_token: your tushare pro token
      gap_threshold: e.g. 0.07 for 7% high open
      vol_multiplier_threshold: matched volume / avg_min >= this
      max_pullback: allowed pullback during auction (if provided by API)
      workers: number of threads fetching per-stock daily vol (speed up)
      sleep_per_call: polite sleep between API calls to avoid rate limit (adjust if needed)

    Returns:
      pandas.DataFrame with columns: ts_code, gm_symbol, trade_date, pre_close, match_price, match_volume, gap, vol_mult, pullback
    """
    ts.set_token(tushare_token)
    pro = ts.pro_api()

    # 1) Get auction data for the date
    # Prefer open-auction interface; fallback to stk_auction
    try:
        df = pro.stk_auction_o(trade_date=trade_date)
        if df is None or df.empty:
            df = pro.stk_auction(trade_date=trade_date)
    except Exception as e:
        # fallback
        try:
            df = pro.stk_auction(trade_date=trade_date)
        except Exception as e2:
            raise RuntimeError("无法调用 TuShare 的集合竞价接口，请确认 token 权限和接口名") from e2

    if df is None or df.empty:
        return pd.DataFrame()

    # Normalize columns: try to find fields
    df_cols = [c.lower() for c in df.columns]
    # candidate field names
    pre_close_candidates = ['pre_close', 'pre_close_price', 'pre_close_px', 'last_close']
    match_price_candidates = ['match_price', 'match_px', 'price', 'match_prc']
    match_vol_candidates = ['match_vol', 'match_volume', 'match_volumn', 'match_qty']

    def pick_val(row, candidates, default=0.0):
        for c in candidates:
            if c in row.index:
                return safe_float(row[c])
        return default

    # 2) For each auction row, compute gap and prepare to compute vol multiplier:
    hits = []
    # We'll parallel fetch avg daily vols for each ts_code (20-day avg)
    ts_codes = df.get('ts_code', df.get('code', pd.Series())).astype(str).tolist()

    # fetch 20-day avg daily volume for each ts_code in parallel
    def fetch_avg20(ts_code):
        try:
            # Pull last 40 days to ensure 20 tradable days
            hist = pro.daily(ts_code=ts_code, start_date=(pd.to_datetime(trade_date)-pd.Timedelta(days=60)).strftime("%Y%m%d"),
                             end_date=trade_date, fields='trade_date,vol')
            if hist is None or hist.empty:
                return ts_code, None
            vols = hist['vol'].astype(float).values
            if len(vols) >= 20:
                avg20 = float(pd.Series(vols[-20:]).mean())
            else:
                avg20 = float(pd.Series(vols).mean())
            return ts_code, avg20
        except Exception as ex:
            # On error return None
            return ts_code, None

    avg20_map = {}
    # Use threadpool to speed up many pro.daily calls (careful with rate limits)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(fetch_avg20, code): code for code in ts_codes}
        for fut in tqdm(as_completed(futures), total=len(futures), desc="fetch avg20"):
            code = futures[fut]
            try:
                code_ret, avg20 = fut.result()
                avg20_map[code_ret] = avg20
            except Exception:
                avg20_map[code] = None
            # polite sleep to avoid throttling
            time.sleep(sleep_per_call)

    # 3) Evaluate each auction row
    for idx, row in df.iterrows():
        try:
            ts_code = row.get('ts_code') or row.get('code') or None
            if ts_code is None:
                continue
            pre_close = pick_val(row, pre_close_candidates, default=np.nan)
            match_price = pick_val(row, match_price_candidates, default=np.nan)
            match_volume = pick_val(row, match_vol_candidates, default=0.0)
            if pd.isna(pre_close) or pre_close == 0 or pd.isna(match_price):
                continue
            gap = float(match_price) / float(pre_close) - 1.0
            avg_daily = avg20_map.get(ts_code, None)
            avg_min = (avg_daily / 240.0) if (avg_daily and avg_daily > 0) else 1.0
            vol_mult = float(match_volume) / (avg_min + 1e-9)
            # pullback if available
            low_px = row.get('low_price') or row.get('min_price') or None
            if low_px:
                pullback = float(low_px) / float(match_price) - 1.0
            else:
                pullback = 0.0

            if gap >= gap_threshold and vol_mult >= vol_multiplier_threshold and pullback >= -max_pullback:
                hits.append({
                    'ts_code': ts_code,
                    'gm_symbol': ts_to_gm(ts_code),
                    'trade_date': trade_date,
                    'pre_close': pre_close,
                    'match_price': match_price,
                    'match_volume': match_volume,
                    'gap': gap,
                    'vol_mult': vol_mult,
                    'pullback': pullback
                })
        except Exception:
            continue

    return pd.DataFrame(hits)


# -------------------------- 2) EmQuant / GM API minute-based fallback (needs symbol list) --------------------------
def get_candidates_via_gm_minute(symbol_list,
                                 date_str,
                                 gap_threshold=0.07,
                                 vol_multiplier_threshold=3.0,
                                 first_minutes=10,
                                 gm_sleep=0.05):
    """
    Fallback: if you cannot use TuShare's auction API, but you have a list of symbols and access
    to EmQuant/GM API history queries, approximate the auction by using the first minute's open
    and first N minutes' total volume.

    NOTE: This function assumes you run it in an environment with gm.api available and authenticated.
    It uses gm.history_n or history functions available in GM API. Because gm.api usage varies by environment,
    this is a template and may need small adjustments.

    Args:
      symbol_list: list of 'SZSE.000001' style symbols
      date_str: 'YYYY-MM-DD' or date object
    Returns:
      pandas.DataFrame of hits
    """
    from gm.api import history_n
    import pandas as pd
    hits = []
    for s in symbol_list:
        try:
            # get prev close
            prev_df = history_n(symbol=s, frequency='1d', count=2, end_time=date_str, fill_missing='last', df=True)
            if prev_df is None or len(prev_df) < 2:
                continue
            prev_close = float(prev_df['close'].iloc[-2])
            # get first minute bar of the day (approximate auction)
            minute_df = history_n(symbol=s, frequency='60s', count=first_minutes, end_time=date_str + " 15:00:00", fill_missing='last', df=True)
            if minute_df is None or len(minute_df) == 0:
                continue
            # minute_df is ordered; first row corresponds to first minute
            first_open = float(minute_df['open'].iloc[0])
            match_price = first_open
            gap = first_open / prev_close - 1.0
            firstN_vol = minute_df['volume'].astype(float).iloc[:first_minutes].sum()
            # get daily avg20 as baseline
            hist_daily = history_n(symbol=s, frequency='1d', count=25, end_time=date_str, fill_missing='last', df=True)
            if hist_daily is None or len(hist_daily) == 0:
                avg_min = 1.0
            else:
                vols = hist_daily['volume'].astype(float)
                avg_daily = vols.tail(20).mean() if len(vols) >= 20 else vols.mean()
                avg_min = avg_daily / 240.0 if avg_daily > 0 else 1.0
            vol_mult = firstN_vol / (avg_min + 1e-9)
            min_close = minute_df['close'].astype(float).iloc[:first_minutes].min()
            pullback = min_close / first_open - 1.0
            if gap >= gap_threshold and vol_mult >= vol_multiplier_threshold and pullback >= -0.05:
                hits.append({
                    'symbol': s,
                    'date': date_str,
                    'gap': gap,
                    'firstN_vol': firstN_vol,
                    'vol_mult': vol_mult,
                    'pullback': pullback
                })
            # polite sleep to avoid platform throttling
            time.sleep(gm_sleep)
        except Exception:
            continue
    return pd.DataFrame(hits)


# -------------------------- 3) same reason: iFinD / DataFeed (THS) placeholder (伪代码) --------------------------
def ifind_placeholder_open_auction(datafeed_client, date_str, gap_threshold=0.07, vol_mult=3.0):
    """
    PSEUDOCODE for iFinD / THS DataFeed or other vendor:
    DataFeed often exposes an 'open_auction' event or an API to fetch day's auction snapshot for all subscribed symbols.
    The concrete SDK varies by vendor; below is a conceptual snippet — adapt to your SDK.

    Args:
      datafeed_client: your initialized DataFeed client object (vendor-specific)
    Returns:
      DataFrame of hits (ts_code/symbol, match_price, match_volume, gap, vol_mult)
    """
    # PSEUDOCODE - replace with vendor SDK calls
    # auctions = datafeed_client.get_open_auction_snapshot(date=date_str)  # vendor-specific
    # for symbol, auction in auctions.items():
    #     match_price = auction['match_price']
    #     match_volume = auction['match_volume']
    #     pre_close = auction['pre_close']
    #     gap = match_price / pre_close - 1.0
    #     vol_mult = match_volume / (vendor_provided_avg_min or computed baseline)
    #     if gap >= gap_threshold and vol_mult >= vol_mult_threshold:
    #         append hit
    raise NotImplementedError("This is a placeholder. Implement using your iFinD / DataFeed SDK per vendor docs.")


# -------------------------- Example usage / CLI-like helpers --------------------------
if __name__ == '__main__':
    # Example: use TuShare to get candidates for today
    # NOTE: set your token below
    TUSHARE_TOKEN = "cfd2ce508529b10af4663dd912613b19927e63766eab996a3eeeb967"
    today = pd.Timestamp.now().strftime("%Y%m%d")
    print("Running TuShare auction screener for", today)
    df_hits = get_auction_candidates_tushare(trade_date=today,
                                             tushare_token=TUSHARE_TOKEN,
                                             gap_threshold=0.07,
                                             vol_multiplier_threshold=3.0,
                                             max_pullback=0.05,
                                             workers=6,
                                             sleep_per_call=0.09)
    print("Found", len(df_hits), "hits")
    if len(df_hits) > 0:
        out = f"candidates_{today}.csv"
        df_hits.to_csv(out, index=False, encoding='utf-8-sig')
        print("Saved", out)
