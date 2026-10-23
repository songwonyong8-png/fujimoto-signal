"""Download adjusted-for-splits? No: raw OHLCV (auto_adjust=False) for reproducible close-price indicators."""
import json
from datetime import datetime, timezone
from pathlib import Path
import yfinance as yf
ROOT=Path(__file__).resolve().parent/'data';ROOT.mkdir(exist_ok=True)
for symbol in ('DRAM','NVDA','MU','AMD'):
    try:
        df=yf.download(symbol,period='1y',interval='1d',auto_adjust=False,progress=False,threads=False)
        if df.empty: raise ValueError('No data')
        if isinstance(df.columns, __import__('pandas').MultiIndex):df.columns=df.columns.get_level_values(0)
        df=df.dropna(subset=['Open','High','Low','Close','Volume'])
        rows=[{'date':str(idx.date()),'open':round(float(r['Open']),4),'high':round(float(r['High']),4),'low':round(float(r['Low']),4),'close':round(float(r['Close']),4),'volume':int(r['Volume'])} for idx,r in df.iterrows()]
        if len(rows)<60:raise ValueError('Insufficient rows')
        (ROOT/f'{symbol}.json').write_text(json.dumps({'ticker':symbol,'updated_at':datetime.now(timezone.utc).isoformat(),'rows':rows},ensure_ascii=False),encoding='utf-8')
        print(symbol,len(rows),rows[-1]['date'])
    except Exception as e:
        print(f'ERROR {symbol}: {e}')
        raise
