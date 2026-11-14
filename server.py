"""FINN local application server. Standard library only; stores state in finn.db."""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path
import json, sqlite3, urllib.request, urllib.error, datetime, re, os, http.cookiejar, html, hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = Path(__file__).resolve().parent
DB = Path(os.environ.get("FINN_DB_PATH", str(ROOT / "finn.db"))).resolve()
PORT = int(os.environ.get("FINN_PORT", "8765"))
HOST = os.environ.get("FINN_HOST", "127.0.0.1")
READ_ONLY = os.environ.get("FINN_READ_ONLY", "0").lower() in ("1", "true", "yes")
COMPANIES = [
 ("RELIANCE","Reliance Industries","Energy · Retail"),("HDFCBANK","HDFC Bank","Financials"),("TCS","Tata Consultancy Services","Technology"),("ICICIBANK","ICICI Bank","Financials"),("INFY","Infosys","Technology"),("BHARTIARTL","Bharti Airtel","Telecom"),("ITC","ITC","Consumer"),("LT","Larsen & Toubro","Industrials"),("TMPV","Tata Motors Passenger Vehicles","Automotive · EV"),("SUNPHARMA","Sun Pharma","Healthcare"),("TATASTEEL","Tata Steel","Materials"),("MARUTI","Maruti Suzuki","Automotive"),("TRENT","Trent","Consumer"),("ASIANPAINT","Asian Paints","Consumer"),("HINDUNILVR","Hindustan Unilever","Consumer"),("AXISBANK","Axis Bank","Financials"),("TITAN","Titan Company","Consumer"),("TMCV","Tata Motors Commercial Vehicles","Automotive · Commercial vehicles"),("ETERNAL","Eternal Limited","Consumer · Technology")]
PEOPLE = [
 ("Priya Menon","PM","VP Operations · Formerly Tata Motors EV","Automotive · EV · Supply chain","Led supplier localisation for an EV platform. Synthetic profile."),
 ("Arjun Rao","AR","Partner · Growth equity · Former HDFC Bank","Financials · Lending · Risk","Worked with a bank director on a credit committee. Synthetic profile."),
 ("Sonal Kapoor","SK","Independent advisor · Consumer retail","Consumer · Retail · Store operations","Built regional operations at a national retail chain. Synthetic profile."),
 ("Nikhil Varma","NV","Director · Industrial strategy · Former L&T","Industrials · Capex · EPC","Worked on supplier qualification during a capacity build. Synthetic profile."),
 ("Meera Joshi","MJ","Former CFO · Listed chemicals company","Finance · Governance · Chemicals","Finance leader with experience in capital allocation. Synthetic profile.")]
EVENTS = [
 ("TMPV","Management","high","New group CFO appointed; transition begins 1 December","Illustrative filing readout. The profile and date are simulated.","09:42"),
 ("HDFCBANK","Results","high","Q2 results: profit growth outpaces revenue; margin narrows","Illustrative results summary. Financial figures are simulated.","08:18"),
 ("LT","Capex","medium","Board approves expansion at precision manufacturing unit","Illustrative notice; project assumptions are simulated.","Yesterday"),
 ("RELIANCE","Credit rating","routine","Rating reaffirmed; outlook maintained at stable","Illustrative rating notice. No live filing is attached.","Yesterday"),
 ("TRENT","Press release","medium","New store format to launch in three additional cities","Illustrative company release. Data is simulated.","Yesterday"),
 ("INFY","Dividend","routine","Interim dividend record date announced","Illustrative exchange filing.","2 days ago"),
 ("SUNPHARMA","M&A","high","Subsidiary signs agreement to acquire specialty portfolio","Illustrative filing; transaction information is simulated.","2 days ago")]

def connect():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c

def init_db():
    with connect() as c:
        c.executescript('''CREATE TABLE IF NOT EXISTS companies(ticker TEXT PRIMARY KEY,name TEXT NOT NULL,sector TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,ticker TEXT NOT NULL,category TEXT NOT NULL,priority TEXT NOT NULL,title TEXT NOT NULL,summary TEXT NOT NULL,occurred TEXT NOT NULL,source TEXT NOT NULL DEFAULT 'Synthetic demo',created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS people(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,initials TEXT NOT NULL,role TEXT NOT NULL,sectors TEXT NOT NULL,context TEXT NOT NULL,synthetic INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS preferences(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sources(id INTEGER PRIMARY KEY AUTOINCREMENT,ticker TEXT NOT NULL,title TEXT NOT NULL,url TEXT NOT NULL,kind TEXT NOT NULL,added_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS research_notes(id INTEGER PRIMARY KEY AUTOINCREMENT,ticker TEXT NOT NULL,body TEXT NOT NULL,created_at TEXT NOT NULL);''')
        cols={r['name'] for r in c.execute('PRAGMA table_info(events)')}
        if 'source_url' not in cols: c.execute('ALTER TABLE events ADD COLUMN source_url TEXT')
        if 'source_ref' not in cols: c.execute('ALTER TABLE events ADD COLUMN source_ref TEXT')
        c.execute('CREATE UNIQUE INDEX IF NOT EXISTS events_source_ref_unique ON events(source,source_ref) WHERE source_ref IS NOT NULL')
        c.executescript('''CREATE TABLE IF NOT EXISTS company_documents(id INTEGER PRIMARY KEY AUTOINCREMENT,ticker TEXT NOT NULL,title TEXT NOT NULL,url TEXT NOT NULL,kind TEXT NOT NULL,published TEXT,discovered_at TEXT NOT NULL,UNIQUE(ticker,url));
        CREATE TABLE IF NOT EXISTS sync_log(id INTEGER PRIMARY KEY AUTOINCREMENT,source TEXT NOT NULL,status TEXT NOT NULL,records INTEGER NOT NULL,detail TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS market_prices(ticker TEXT NOT NULL,session_date TEXT NOT NULL,close REAL NOT NULL,volume INTEGER,provider TEXT NOT NULL,updated_at TEXT NOT NULL,PRIMARY KEY(ticker,session_date));''')
        if c.execute('SELECT count(*) FROM companies').fetchone()[0]==0:
            c.executemany('INSERT INTO companies(ticker,name,sector) VALUES(?,?,?)',COMPANIES)
        c.executemany('INSERT INTO companies(ticker,name,sector) VALUES(?,?,?) ON CONFLICT(ticker) DO UPDATE SET name=excluded.name,sector=excluded.sector',COMPANIES)
        c.execute("UPDATE companies SET ticker='TMPV',name='Tata Motors Passenger Vehicles',sector='Automotive · EV' WHERE ticker='TATAMOTORS' AND NOT EXISTS(SELECT 1 FROM companies WHERE ticker='TMPV')")
        c.execute("UPDATE events SET ticker='TMPV' WHERE ticker='TATAMOTORS'")
        c.execute("UPDATE companies SET ticker='ETERNAL',name='Eternal Limited',sector='Consumer · Technology' WHERE ticker='ZOMATO' AND NOT EXISTS(SELECT 1 FROM companies WHERE ticker='ETERNAL')")
        c.execute("UPDATE events SET ticker='ETERNAL' WHERE ticker='ZOMATO'")
        c.execute("DELETE FROM companies WHERE ticker IN ('TATAMOTORS','ZOMATO')")
        if c.execute('SELECT count(*) FROM people').fetchone()[0]==0:
            c.executemany('INSERT INTO people(name,initials,role,sectors,context) VALUES(?,?,?,?,?)',PEOPLE)
        if c.execute('SELECT count(*) FROM events').fetchone()[0]==0:
            now=datetime.datetime.now(datetime.timezone.utc).isoformat()
            c.executemany('INSERT INTO events(ticker,category,priority,title,summary,occurred,created_at) VALUES(?,?,?,?,?,?,?)',[(t,cat,p,title,s,when,now) for t,cat,p,title,s,when in EVENTS])
        defaults={'price_threshold':'3','volume_threshold':'2','categories':'["Results","M&A","Management","Litigation","Capex"]'}
        c.executemany('INSERT OR IGNORE INTO preferences(key,value) VALUES(?,?)',defaults.items())
        if c.execute('SELECT count(*) FROM sources').fetchone()[0]==0:
            c.executemany('INSERT INTO sources(ticker,title,url,kind,added_at) VALUES(?,?,?,?,?)',[(t,'Screener company page',f'https://www.screener.in/company/{t}/','reference',datetime.datetime.now(datetime.timezone.utc).isoformat()) for t,_,_ in COMPANIES])

def rows(sql,args=()):
    with connect() as c: return [dict(r) for r in c.execute(sql,args).fetchall()]

def yahoo_quote(ticker):
    symbol=ticker.upper()+'.NS'
    url='https://query1.finance.yahoo.com/v8/finance/chart/'+symbol+'?range=5d&interval=1d'
    req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 FINN-local-demo'})
    with urllib.request.urlopen(req,timeout=8) as res: data=json.loads(res.read())
    result=data.get('chart',{}).get('result')
    if not result: raise ValueError('Quote not available from provider')
    r=result[0]; q=r['indicators']['quote'][0]; closes=[x for x in q.get('close',[]) if x is not None]
    if not closes: raise ValueError('Provider returned no closing prices')
    close=closes[-1]; prev=closes[-2] if len(closes)>1 else close
    return {'ticker':ticker,'symbol':symbol,'price':round(close,2),'change_pct':round((close-prev)/prev*100,2) if prev else 0,'volume':q.get('volume',[None])[-1],'currency':r.get('meta',{}).get('currency','INR'),'provider':'Yahoo Finance','as_of':datetime.datetime.now(datetime.timezone.utc).isoformat(),'simulated':False}

def yahoo_daily_bars(ticker):
    symbol=ticker.upper()+'.NS'
    url='https://query1.finance.yahoo.com/v8/finance/chart/'+symbol+'?range=1mo&interval=1d'
    req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 FINN-local-demo'})
    with urllib.request.urlopen(req,timeout=12) as res: data=json.loads(res.read())
    result=data.get('chart',{}).get('result')
    if not result: raise ValueError('Yahoo Finance returned no daily history')
    r=result[0]; q=r['indicators']['quote'][0]; bars=[]
    for ts,close,volume in zip(r.get('timestamp',[]),q.get('close',[]),q.get('volume',[])):
        if close is None: continue
        day=datetime.datetime.fromtimestamp(ts,datetime.timezone.utc).date().isoformat()
        bars.append((day,float(close),int(volume) if volume is not None else None))
    if not bars: raise ValueError('Yahoo Finance returned no daily closes')
    return symbol,bars

def sync_prices():
    portfolio=[r['ticker'] for r in rows('SELECT ticker FROM companies WHERE active=1 ORDER BY ticker')]
    prefs={r['key']:r['value'] for r in rows('SELECT key,value FROM preferences')}
    try: price_limit=max(.1,float(prefs.get('price_threshold','3')))
    except (ValueError,TypeError): price_limit=3
    try: volume_limit=max(1,float(prefs.get('volume_threshold','2')))
    except (ValueError,TypeError): volume_limit=2
    inserted=0; failures=[]; now=datetime.datetime.now(datetime.timezone.utc).isoformat()
    def fetch(t): return t,yahoo_daily_bars(t)
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures=[pool.submit(fetch,t) for t in portfolio]
        for future in as_completed(futures):
            try: ticker,(symbol,bars)=future.result()
            except Exception as e:
                failures.append(str(e)[:200]); continue
            with connect() as c:
                c.executemany('INSERT INTO market_prices(ticker,session_date,close,volume,provider,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(ticker,session_date) DO UPDATE SET close=excluded.close,volume=excluded.volume,provider=excluded.provider,updated_at=excluded.updated_at',[(ticker,d,close,volume,'Yahoo Finance',now) for d,close,volume in bars])
                close=bars[-1][1]; day=bars[-1][0]; prev=bars[-2][1] if len(bars)>1 else close
                pct=(close-prev)/prev*100 if prev else 0
                volumes=[v for _,_,v in bars[-21:-1] if v is not None]
                latest_volume=bars[-1][2]
                checks=[]
                if abs(pct)>=price_limit: checks.append(('Price move',f'{pct:+.2f}% session move crossed your ±{price_limit:g}% threshold.',f'{pct:+.2f}%'))
                if volumes and latest_volume is not None:
                    avg=sum(volumes)/len(volumes); multiple=latest_volume/avg if avg else 0
                    if multiple>=volume_limit: checks.append(('Volume spike',f'{multiple:.1f}× 20-session average volume crossed your {volume_limit:g}× threshold.',f'{multiple:.1f}×'))
                for cat,summary,move in checks:
                    ref=f'market:{ticker}:{day}:{cat.lower().replace(" ","-")}'
                    cur=c.execute('INSERT OR IGNORE INTO events(ticker,category,priority,title,summary,occurred,source,created_at,source_url,source_ref) VALUES(?,?,?,?,?,?,?,?,?,?)',(ticker,cat,'high',f'{ticker}: {cat.lower()} threshold crossed',summary,day,'Yahoo Finance EOD',now,f'https://finance.yahoo.com/quote/{symbol}/history/',ref))
                    inserted+=cur.rowcount
    with connect() as c:
        c.execute('INSERT INTO sync_log(source,status,records,detail,created_at) VALUES(?,?,?,?,?)',('Yahoo Finance EOD','ok' if not failures else 'partial',inserted,f'{len(portfolio)-len(failures)}/{len(portfolio)} tickers refreshed; {inserted} new threshold alerts; {len(failures)} provider errors.',now))
    return {'source':'Yahoo Finance daily chart','tickers':len(portfolio),'updated':len(portfolio)-len(failures),'alerts':inserted,'errors':failures[:5]}

def nse_json(url):
    jar=http.cookiejar.CookieJar(); opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    headers={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36','Accept':'application/json, text/plain, */*','Accept-Language':'en-US,en;q=0.9','Referer':'https://www.nseindia.com/companies-listing/corporate-filings-announcements'}
    opener.open(urllib.request.Request('https://www.nseindia.com/companies-listing/corporate-filings-announcements',headers=headers),timeout=12).read(1024)
    with opener.open(urllib.request.Request(url,headers=headers),timeout=20) as response: return json.loads(response.read())

def nse_quote(ticker):
    symbol=ticker.upper()
    data=nse_json('https://www.nseindia.com/api/quote-equity?symbol='+urllib.parse.quote(symbol))
    info=data.get('priceInfo') or {}
    price=info.get('lastPrice')
    if price is None: raise ValueError('NSE response did not include a last price')
    return {'ticker':symbol,'symbol':symbol+'.NS','price':float(price),'change_pct':float(info.get('pChange') or 0),'volume':(data.get('marketDeptOrderBook') or {}).get('tradeInfo',{}).get('totalTradedVolume'),'currency':'INR','provider':'NSE India','as_of':data.get('metadata',{}).get('lastUpdateTime') or datetime.datetime.now(datetime.timezone.utc).isoformat(),'simulated':False}

def classify_announcement(subject,desc):
    text=(subject+' '+desc).lower()
    checks=[('Results',('financial results','quarterly results','audited results','unaudited results','outcome of board meeting')),
    ('M&A',('acquisition','acquire','merger','demerger','joint venture','scheme of arrangement')),
    ('Management',('appointment of','resignation','cessation','appointed as','change in director','key managerial')),
    ('Litigation',('order passed','penalty','fine','show cause','insolvency','litigation','sebi order')),
    ('Capex',('capital expenditure','capex','capacity expansion','new plant','manufacturing facility')),
    ('Dividend',('dividend','record date')),
    ('Credit rating',('credit rating','rating reaffirmed','rating upgraded','rating downgraded')),
    ('M&A',('buyback','preferential issue','rights issue','qualified institutions placement','qip')),
    ('Earnings call',('earnings call','conference call','transcript'))]
    for label,terms in checks:
        if any(word in text for word in terms): return label
    return 'Press release'

def sync_nse_announcements():
    data=nse_json('https://www.nseindia.com/api/corporate-announcements?index=equities')
    if isinstance(data,dict): data=data.get('data') or data.get('records') or []
    if not isinstance(data,list): raise ValueError('NSE returned an unexpected announcement response')
    portfolio={r['ticker'] for r in rows('SELECT ticker FROM companies WHERE active=1')}; inserted=0; scanned=0
    with connect() as c:
        c.execute("DELETE FROM events WHERE source='Synthetic demo'")
        for item in data:
            ticker=str(item.get('symbol') or item.get('symbolName') or '').upper().strip()
            if ticker not in portfolio: continue
            scanned+=1
            subject=str(item.get('desc') or item.get('subject') or item.get('sm_name') or 'Company announcement').strip()
            details=str(item.get('attchmntText') or item.get('details') or item.get('news') or '').strip()
            attachment=str(item.get('attchmntFile') or item.get('attachment') or item.get('fileUrl') or '').strip()
            if attachment and attachment.startswith('/'): attachment='https://nsearchives.nseindia.com'+attachment
            if attachment and not attachment.startswith('https://'): attachment=''
            category=classify_announcement(subject,details)
            priority='high' if category in ('Results','M&A','Management','Litigation') else ('medium' if category in ('Capex','Credit rating') else 'routine')
            raw_date=str(item.get('an_dt') or item.get('broadcastDateTime') or item.get('dt') or item.get('sort_date') or 'Live NSE filing')
            unique=str(item.get('seq_id') or item.get('newsId') or item.get('id') or hashlib.sha256((ticker+raw_date+subject+attachment).encode()).hexdigest()[:24])
            source_url=attachment or f'https://www.nseindia.com/companies-listing/corporate-filings-announcements?symbol={ticker}'
            summary=details or subject
            title=subject[:400]
            cur=c.execute('INSERT OR IGNORE INTO events(ticker,category,priority,title,summary,occurred,source,created_at,source_url,source_ref) VALUES(?,?,?,?,?,?,?,?,?,?)',(ticker,category,priority,title,summary,raw_date,'NSE official filing',datetime.datetime.now(datetime.timezone.utc).isoformat(),source_url,unique))
            inserted+=cur.rowcount
        c.execute('INSERT INTO sync_log(source,status,records,detail,created_at) VALUES(?,?,?,?,?)',('NSE announcements','ok',inserted,f'{scanned} portfolio filings checked; {inserted} new records stored.',datetime.datetime.now(datetime.timezone.utc).isoformat()))
    return {'source':'NSE India corporate announcements','source_url':'https://www.nseindia.com/companies-listing/corporate-filings-announcements','received':len(data),'portfolio_matches':scanned,'inserted':inserted}

class LinkParser(__import__('html.parser',fromlist=['HTMLParser']).HTMLParser):
    def __init__(self): super().__init__(); self.links=[]; self.active=None
    def handle_starttag(self,tag,attrs):
        if tag.lower()=='a':
            d=dict(attrs); href=d.get('href',''); title=' '.join((d.get('title',''),d.get('aria-label',''))).strip()
            self.active=[href,title]
    def handle_data(self,data):
        if self.active is not None and data.strip(): self.active[1]+=' '+data.strip()
    def handle_endtag(self,tag):
        if tag.lower()=='a' and self.active is not None:
            if self.active[0]: self.links.append((self.active[0],' '.join(self.active[1].split())))
            self.active=None

def discover_company_documents(ticker):
    url='https://www.screener.in/company/'+urllib.parse.quote(ticker.upper())+'/'
    req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 FINN research link discovery'})
    with urllib.request.urlopen(req,timeout=15) as response: page=response.read(3_000_000).decode('utf-8','replace')
    parser=LinkParser(); parser.feed(page)
    found=[]
    for href,title in parser.links:
        absolute=urllib.parse.urljoin(url,html.unescape(href)); label=(title+' '+absolute).lower()
        if not absolute.startswith('https://'): continue
        kind='annual report' if 'annual' in label and ('report' in label or absolute.lower().endswith('.pdf')) else ('concall / transcript' if any(k in label for k in ('concall','conference-call','transcript','earnings-call')) else '')
        if kind: found.append((title or kind,absolute,kind))
    seen=set(); found=[x for x in found if not (x[1] in seen or seen.add(x[1]))]
    with connect() as c:
        for title,link,kind in found: c.execute('INSERT OR IGNORE INTO company_documents(ticker,title,url,kind,published,discovered_at) VALUES(?,?,?,?,?,?)',(ticker.upper(),title[:300],link,kind,None,datetime.datetime.now(datetime.timezone.utc).isoformat()))
        c.execute('INSERT INTO sync_log(source,status,records,detail,created_at) VALUES(?,?,?,?,?)',('Screener document links','ok',len(found),f'{ticker.upper()}: {len(found)} primary-document links discovered; source URLs are retained for review.',datetime.datetime.now(datetime.timezone.utc).isoformat()))
    return {'ticker':ticker.upper(),'count':len(found),'documents':rows('SELECT * FROM company_documents WHERE ticker=? ORDER BY kind,title',(ticker.upper(),)),'discovery_page':url}

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs): super().__init__(*args,directory=str(ROOT),**kwargs)
    def log_message(self,fmt,*args): print('%s - %s' % (self.address_string(),fmt%args))
    def send_json(self,obj,status=200):
        data=json.dumps(obj,ensure_ascii=False).encode(); self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(data))); self.send_header('Access-Control-Allow-Origin','*'); self.end_headers(); self.wfile.write(data)
    def body(self):
        n=int(self.headers.get('Content-Length','0')); return json.loads(self.rfile.read(n) or b'{}')
    def do_OPTIONS(self): self.send_response(204); self.send_header('Access-Control-Allow-Origin','*'); self.send_header('Access-Control-Allow-Methods','GET,POST,PUT,DELETE,OPTIONS'); self.send_header('Access-Control-Allow-Headers','Content-Type'); self.end_headers()
    def do_GET(self):
        u=urlparse(self.path); path=u.path; q=parse_qs(u.query)
        if path=='/api/health': return self.send_json({'ok':True,'app':'FINN','database':str(DB.name),'time':datetime.datetime.now(datetime.timezone.utc).isoformat()})
        if path=='/api/bootstrap':
            prefs={}
            for item in rows('SELECT key,value FROM preferences'):
                try: prefs[item['key']]=json.loads(item['value'])
                except (ValueError,TypeError): prefs[item['key']]=item['value']
            last_sync=rows("SELECT * FROM sync_log WHERE source='NSE announcements' ORDER BY id DESC LIMIT 1")
            market=rows('''SELECT m.ticker,m.session_date,m.close,m.volume,m.provider,
                CASE WHEN p.close IS NOT NULL AND p.close<>0 THEN ROUND((m.close-p.close)*100.0/p.close,2) END AS change_pct
                FROM market_prices m LEFT JOIN market_prices p ON p.ticker=m.ticker AND p.session_date=(SELECT MAX(x.session_date) FROM market_prices x WHERE x.ticker=m.ticker AND x.session_date<m.session_date)
                WHERE m.session_date=(SELECT MAX(y.session_date) FROM market_prices y WHERE y.ticker=m.ticker)''')
            last_price_sync=rows("SELECT * FROM sync_log WHERE source='Yahoo Finance EOD' ORDER BY id DESC LIMIT 1")
            return self.send_json({'companies':rows('SELECT * FROM companies WHERE active=1 ORDER BY name'),'events':rows('SELECT * FROM events ORDER BY id DESC'),'people':rows('SELECT * FROM people ORDER BY name'),'preferences':prefs,'market_data':market,'read_only':READ_ONLY,'last_nse_sync':last_sync[0] if last_sync else None,'last_price_sync':last_price_sync[0] if last_price_sync else None,'source_mode':'NSE announcements and Yahoo Finance EOD prices are synced on demand; quotes are fetched on request'})
        if path=='/api/companies': return self.send_json(rows('SELECT * FROM companies ORDER BY name'))
        if path=='/api/events': return self.send_json(rows('SELECT * FROM events ORDER BY id DESC'))
        if path=='/api/sync/status': return self.send_json(rows('SELECT * FROM sync_log ORDER BY id DESC LIMIT 20'))
        if path=='/api/network':
            term=' '.join(q.get('q',['']).split()).lower()
            ps=rows('SELECT * FROM people ORDER BY name')
            return self.send_json([p for p in ps if not term or term in ' '.join(str(v) for v in p.values()).lower()])
        if path.startswith('/api/quote/'):
            ticker=re.sub('[^A-Z0-9]','',path.rsplit('/',1)[-1].upper().removesuffix('.NS').removesuffix('.BO'))
            try: return self.send_json(nse_quote(ticker))
            except Exception as primary_error:
                try:
                    quote=yahoo_quote(ticker); quote['provider']='Yahoo Finance (NSE fallback)'; quote['primary_error']=str(primary_error); return self.send_json(quote)
                except Exception as fallback_error: return self.send_json({'ticker':ticker,'error':str(fallback_error),'primary_error':str(primary_error),'hint':'The NSE quote endpoint and Yahoo fallback are unavailable.'},502)
        if path.startswith('/api/sources/'):
            ticker=path.rsplit('/',1)[-1].upper(); return self.send_json(rows('SELECT * FROM sources WHERE ticker=? ORDER BY id DESC',(ticker,)))
        if path.startswith('/api/research/'):
            ticker=path.rsplit('/',1)[-1].upper(); return self.send_json({'ticker':ticker,'sources':rows('SELECT * FROM sources WHERE ticker=?',(ticker,)),'documents':rows('SELECT * FROM company_documents WHERE ticker=? ORDER BY kind,title',(ticker,)),'notes':rows('SELECT * FROM research_notes WHERE ticker=? ORDER BY id DESC',(ticker,)),'notice':'Document links are discovered from Screener; open the linked issuer source to inspect original company documents.'})
        return super().do_GET()
    def do_POST(self):
        p=urlparse(self.path).path; b=self.body()
        allowed_sync=READ_ONLY and (p in ('/api/sync/nse','/api/sync/prices') or bool(re.fullmatch(r'/api/sync/company/[A-Z0-9.]+',p)))
        if READ_ONLY and not allowed_sync: return self.send_json({'error':'This shared demo is read-only.'},403)
        try:
            if p=='/api/sync/nse':
                try: return self.send_json(sync_nse_announcements())
                except Exception as e:
                    with connect() as c: c.execute('INSERT INTO sync_log(source,status,records,detail,created_at) VALUES(?,?,?,?,?)',('NSE announcements','error',0,str(e)[:500],datetime.datetime.now(datetime.timezone.utc).isoformat()))
                    return self.send_json({'error':'NSE sync failed: '+str(e),'source_url':'https://www.nseindia.com/companies-listing/corporate-filings-announcements'},502)
            if p=='/api/sync/prices':
                try: return self.send_json(sync_prices())
                except Exception as e:
                    with connect() as c: c.execute('INSERT INTO sync_log(source,status,records,detail,created_at) VALUES(?,?,?,?,?)',('Yahoo Finance EOD','error',0,str(e)[:500],datetime.datetime.now(datetime.timezone.utc).isoformat()))
                    return self.send_json({'error':'EOD price sync failed: '+str(e)},502)
            m=re.fullmatch(r'/api/sync/company/([A-Z0-9.]+)',p)
            if m:
                try: return self.send_json(discover_company_documents(m.group(1)))
                except Exception as e:
                    with connect() as c: c.execute('INSERT INTO sync_log(source,status,records,detail,created_at) VALUES(?,?,?,?,?)',('Screener document links','error',0,str(e)[:500],datetime.datetime.now(datetime.timezone.utc).isoformat()))
                    return self.send_json({'error':'Document discovery failed: '+str(e),'source_url':'https://www.screener.in/company/'+m.group(1)+'/'},502)
            if p=='/api/events':
                required=['ticker','category','priority','title','summary']
                if any(not str(b.get(k,'')).strip() for k in required): return self.send_json({'error':'ticker, category, priority, title and summary are required'},400)
                with connect() as c:
                    cur=c.execute('INSERT INTO events(ticker,category,priority,title,summary,occurred,source,created_at) VALUES(?,?,?,?,?,?,?,?)',(b['ticker'].upper(),b['category'],b['priority'],b['title'],b['summary'],b.get('occurred','09:45'),b.get('source','User supplied'),datetime.datetime.now(datetime.timezone.utc).isoformat())); row=dict(c.execute('SELECT * FROM events WHERE id=?',(cur.lastrowid,)).fetchone())
                return self.send_json(row,201)
            if p=='/api/network':
                with connect() as c:
                    cur=c.execute('INSERT INTO people(name,initials,role,sectors,context,synthetic) VALUES(?,?,?,?,?,?)',(b['name'],b.get('initials',''.join(x[0] for x in b['name'].split()[:2]).upper()),b.get('role',''),b.get('sectors',''),b.get('context','User added profile'),int(bool(b.get('synthetic',False))))); row=dict(c.execute('SELECT * FROM people WHERE id=?',(cur.lastrowid,)).fetchone())
                return self.send_json(row,201)
            if p=='/api/sources':
                if not b.get('ticker') or not b.get('url') or not b.get('title'): return self.send_json({'error':'ticker, title and url are required'},400)
                if not b['url'].startswith('https://'): return self.send_json({'error':'Only HTTPS source links are accepted'},400)
                with connect() as c:
                    cur=c.execute('INSERT INTO sources(ticker,title,url,kind,added_at) VALUES(?,?,?,?,?)',(b['ticker'].upper(),b['title'],b['url'],b.get('kind','primary'),datetime.datetime.now(datetime.timezone.utc).isoformat())); row=dict(c.execute('SELECT * FROM sources WHERE id=?',(cur.lastrowid,)).fetchone())
                return self.send_json(row,201)
            if p=='/api/research/notes':
                with connect() as c:
                    cur=c.execute('INSERT INTO research_notes(ticker,body,created_at) VALUES(?,?,?)',(b['ticker'].upper(),b['body'],datetime.datetime.now(datetime.timezone.utc).isoformat())); row=dict(c.execute('SELECT * FROM research_notes WHERE id=?',(cur.lastrowid,)).fetchone())
                return self.send_json(row,201)
            if p=='/api/preferences':
                with connect() as c:
                    for k,v in b.items(): c.execute('INSERT INTO preferences(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(k,json.dumps(v)))
                return self.send_json({'saved':True,'preferences':b})
            return self.send_json({'error':'Unknown API route'},404)
        except (KeyError,ValueError,sqlite3.Error) as e: return self.send_json({'error':str(e)},400)
    def do_DELETE(self):
        p=urlparse(self.path).path; m=re.fullmatch(r'/api/(events|network|sources|research/notes)/(\d+)',p)
        if not m: return self.send_json({'error':'Unknown API route'},404)
        table={'events':'events','network':'people','sources':'sources','research/notes':'research_notes'}[m.group(1)]
        with connect() as c: cur=c.execute(f'DELETE FROM {table} WHERE id=?',(int(m.group(2)),))
        return self.send_json({'deleted':cur.rowcount>0})

if __name__=='__main__':
        init_db(); print(f'FINN running at http://{HOST}:{PORT}  (Ctrl+C to stop)'); ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()
