"""FINN local application server. Standard library only; stores state in finn.db."""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path
import json, sqlite3, urllib.request, urllib.error, datetime, re, os, http.cookiejar, html, hashlib
import io, ipaddress, zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser

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
PROFILE_TAGS={"Priya Menon":["TMPV","TMCV","EV supply chain","Supplier operations"],"Arjun Rao":["HDFCBANK","ICICIBANK","Lending","Credit committees","second degree"],"Sonal Kapoor":["TRENT","Retail","Store operations"],"Nikhil Varma":["LT","TATASTEEL","Industrials","Capex"],"Meera Joshi":["Finance","Governance","CFO","specialty chemicals"]}
DIRECT_NETWORK_LINKS={"TMPV":"Priya Menon","TMCV":"Priya Menon","HDFCBANK":"Arjun Rao","ICICIBANK":"Arjun Rao","TRENT":"Sonal Kapoor","LT":"Nikhil Varma","TATASTEEL":"Nikhil Varma"}
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
        CREATE TABLE IF NOT EXISTS company_document_index(document_id INTEGER PRIMARY KEY,page_count INTEGER NOT NULL,char_count INTEGER NOT NULL,indexed_at TEXT NOT NULL,error TEXT);
        CREATE TABLE IF NOT EXISTS document_pages(document_id INTEGER NOT NULL,page_no INTEGER NOT NULL,text TEXT NOT NULL,PRIMARY KEY(document_id,page_no));
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

def network_context(ticker,topic=''):
    direct=DIRECT_NETWORK_LINKS.get(ticker.upper()); people=rows('SELECT * FROM people ORDER BY name'); matches=[]
    if direct:
        person=next((p for p in people if p['name']==direct),None)
        if person: matches.append({'name':person['name'],'why':person['context'],'match':'Synthetic overlap','synthetic':bool(person['synthetic'])})
    if matches: return matches
    company=next(iter(rows('SELECT sector FROM companies WHERE ticker=?',(ticker.upper(),))),None)
    sector_tokens=set(re.findall(r'[a-z]{4,}',((company or {}).get('sector','')+' '+topic).lower()))
    for person in people:
        profile_tokens=set(re.findall(r'[a-z]{4,}',(person['sectors']+' '+person['role']).lower()))
        overlap=sector_tokens & profile_tokens
        if overlap:
            is_synthetic=bool(person['synthetic'])
            why=f"Synthetic profile tagged {', '.join(sorted(overlap))}; no direct relationship is recorded." if is_synthetic else f"Profile shares the {', '.join(sorted(overlap))} topic; no direct relationship is recorded."
            matches.append({'name':person['name'],'why':why,'match':'Synthetic topic fit' if is_synthetic else 'Sector overlap','synthetic':is_synthetic})
    return matches[:2]

def events_with_network():
    events=rows('SELECT * FROM events ORDER BY id DESC')
    for event in events: event['network_context']=network_context(event['ticker'],event['category']+' '+event['title']+' '+event['summary'])
    return events

def network_profiles():
    profiles=rows('SELECT * FROM people ORDER BY name')
    for person in profiles: person['tags']=PROFILE_TAGS.get(person['name'],[])
    return profiles

def yahoo_quote(ticker,exchange='NS'):
    symbol=ticker.upper()+'.'+exchange
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
    if 'appointment' in text and 'auditor' in text: return 'Unclassified'
    checks=[('Results',('financial results','quarterly results','audited results','unaudited results','outcome of board meeting','result for the quarter')),
    ('M&A',('acquisition','acquire','merger','demerger','joint venture','scheme of arrangement','sale of stake')),
    ('Fund raise',('buyback','preferential issue','rights issue','qualified institutions placement','qip','commercial paper','private placement','fund raising')),
    ('Management',('appointment of','resignation','cessation','appointed as','change in director','key managerial','chief executive officer','chief financial officer')),
    ('Litigation',('order passed','penalty','fine','show cause','insolvency','litigation','sebi order','regulatory order')),
    ('Insider trading',('trading by designated person','insider trading','disclosure under regulation 7','acquisition/disposal of shares by promoter')),
    ('Earnings call',('earnings call','conference call','transcript','concall')),
    ('Investor meetings',('investor meet','investor meeting','investor conference','analyst meet')),
    ('Credit rating',('credit rating','rating reaffirmed','rating upgraded','rating downgraded')),
    ('Bonus/split',('bonus issue','stock split','sub-division of shares','subdivision of shares')),
    ('Dividend',('dividend','record date')),
    ('Capex',('capital expenditure','capex','capacity expansion','new plant','manufacturing facility')),
    ('Postal ballot',('postal ballot','remote e-voting')),
    ('AGM/EGM',('annual general meeting','extraordinary general meeting')),
    ('Pledging',('pledge of shares','creation of pledge','release of pledge','encumbrance')),
    ('Press release',('order win','launch of new product','new product','business update','press release','partnership'))]
    for label,terms in checks:
        if any(word in text for word in terms): return label
    if re.search(r'\b(?:agm|egm)\b',text): return 'AGM/EGM'
    return 'Unclassified'

def normalize_event_date(value):
    raw=str(value or '').strip()
    if not raw: return 'Live NSE filing'
    try:
        parsed=datetime.datetime.fromisoformat(raw.replace('Z','+00:00'))
        if parsed.tzinfo is None: parsed=parsed.replace(tzinfo=datetime.timezone(datetime.timedelta(hours=5,minutes=30)))
        return parsed.isoformat()
    except ValueError: pass
    for fmt in ('%d-%b-%Y %H:%M:%S','%d-%b-%Y %H:%M','%d-%m-%Y %H:%M:%S','%d-%m-%Y %H:%M','%d-%b-%Y','%d-%m-%Y'):
        try: return datetime.datetime.strptime(raw,fmt).replace(tzinfo=datetime.timezone(datetime.timedelta(hours=5,minutes=30))).isoformat()
        except ValueError: continue
    return raw

def sync_nse_announcements():
    data=nse_json('https://www.nseindia.com/api/corporate-announcements?index=equities')
    if isinstance(data,dict): data=data.get('data') or data.get('records') or []
    if not isinstance(data,list): raise ValueError('NSE returned an unexpected announcement response')
    portfolio={r['ticker'] for r in rows('SELECT ticker FROM companies WHERE active=1')}; inserted=0; scanned=0
    saved=rows("SELECT value FROM preferences WHERE key='categories'")
    try: watched=set(json.loads(saved[0]['value'])) if saved else {'Results','M&A','Management','Litigation','Capex'}
    except (ValueError,TypeError): watched={'Results','M&A','Management','Litigation','Capex'}
    with connect() as c:
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
            priority='high' if category in watched else ('medium' if category in ('Fund raise','Capex','Credit rating','Earnings call','Investor meetings') else 'routine')
            raw_date=str(item.get('an_dt') or item.get('broadcastDateTime') or item.get('dt') or item.get('sort_date') or 'Live NSE filing')
            occurred=normalize_event_date(raw_date)
            unique=str(item.get('seq_id') or item.get('newsId') or item.get('id') or hashlib.sha256((ticker+raw_date+subject+attachment).encode()).hexdigest()[:24])
            source_url=attachment or f'https://www.nseindia.com/companies-listing/corporate-filings-announcements?symbol={ticker}'
            summary=details or subject
            title=subject[:400]
            cur=c.execute('INSERT OR IGNORE INTO events(ticker,category,priority,title,summary,occurred,source,created_at,source_url,source_ref) VALUES(?,?,?,?,?,?,?,?,?,?)',(ticker,category,priority,title,summary,occurred,'NSE official filing',datetime.datetime.now(datetime.timezone.utc).isoformat(),source_url,unique))
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

class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts=[]; self.skip=0
    def handle_starttag(self,tag,attrs):
        if tag.lower() in ('script','style','nav','footer','header'): self.skip+=1
        if not self.skip and tag.lower() in ('p','br','div','li','tr','h1','h2','h3','h4'): self.parts.append('\n')
    def handle_endtag(self,tag):
        if tag.lower() in ('script','style','nav','footer','header') and self.skip: self.skip-=1
    def handle_data(self,data):
        if not self.skip and data.strip(): self.parts.append(data.strip()+'\n')

def public_https_url(url):
    parsed=urlparse(url)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password: return False
    try:
        address=ipaddress.ip_address(parsed.hostname)
        if not address.is_global: return False
    except ValueError: pass
    return True

def extract_document_pages(doc):
    if not public_https_url(doc['url']): raise ValueError('Document link must use a public HTTPS URL')
    req=urllib.request.Request(doc['url'],headers={'User-Agent':'Mozilla/5.0 FINN primary-source reader','Accept':'application/pdf,text/html,text/plain;q=0.9,*/*;q=0.1'})
    with urllib.request.urlopen(req,timeout=18) as response:
        final_url=response.geturl(); content_type=response.headers.get_content_type().lower()
        if not public_https_url(final_url): raise ValueError('Document redirected to a non-public or non-HTTPS URL')
        length=response.headers.get('Content-Length')
        if length and int(length)>15_000_000: raise ValueError('Document exceeds the 15 MB indexing limit')
        raw=response.read(15_000_001)
    if len(raw)>15_000_000: raise ValueError('Document exceeds the 15 MB indexing limit')
    if raw.startswith(b'PK\x03\x04') or content_type in ('application/zip','application/x-zip-compressed'):
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                candidates=[entry for entry in archive.infolist() if not entry.is_dir() and entry.filename.lower().endswith('.pdf')]
                if not candidates: raise ValueError('ZIP archive contains no PDF document')
                member=candidates[0]
                if member.file_size>50_000_000: raise ValueError('PDF inside ZIP exceeds the 50 MB expansion limit')
                raw=archive.read(member)
        except zipfile.BadZipFile as e: raise ValueError('Downloaded ZIP archive is invalid') from e
        if not raw.startswith(b'%PDF-'): raise ValueError('ZIP archive did not contain a readable PDF')
        content_type='application/pdf'
    if raw.startswith(b'%PDF-') or content_type=='application/pdf':
        try:
            from pypdf import PdfReader
        except ImportError as e: raise RuntimeError('PDF indexing requires pypdf. Install requirements.txt and restart FINN.') from e
        reader=PdfReader(io.BytesIO(raw),strict=False)
        if reader.is_encrypted and not reader.decrypt(''): raise ValueError('PDF is encrypted and cannot be indexed')
        if len(reader.pages)>500: raise ValueError('PDF exceeds the 500-page indexing limit')
        pages=[]
        for number,page in enumerate(reader.pages,1):
            text=' '.join((page.extract_text() or '').split())
            if text: pages.append((number,text[:80_000]))
        if not pages: raise ValueError('No extractable text was found; this may be a scanned PDF')
        return pages
    if content_type in ('text/html','application/xhtml+xml'):
        parser=TextExtractor(); parser.feed(raw.decode('utf-8','replace'))
        text=' '.join(' '.join(parser.parts).split())
    elif content_type.startswith('text/'):
        text=' '.join(raw.decode('utf-8','replace').split())
    else: raise ValueError('Unsupported document type; expected PDF or HTML/text')
    if not text: raise ValueError('Document contains no searchable text')
    # HTML transcripts have no stable page numbers. Store bounded sections and cite the source URL.
    return [(n+1,text[i:i+10_000]) for n,i in enumerate(range(0,min(len(text),1_000_000),10_000))]

def index_company_documents(ticker):
    ticker=ticker.upper()
    docs=rows('''SELECT d.*,i.page_count,i.char_count,i.indexed_at,i.error FROM company_documents d
        LEFT JOIN company_document_index i ON i.document_id=d.id WHERE d.ticker=? ORDER BY d.discovered_at DESC,d.id DESC''',(ticker,))
    if not docs: raise ValueError('Find company documents first, then index their source text')
    indexed=0; errors=[]
    for doc in docs[:4]:
        if doc.get('indexed_at') and not doc.get('error'): continue
        try:
            pages=extract_document_pages(doc); char_count=sum(len(text) for _,text in pages)
            with connect() as c:
                c.execute('DELETE FROM document_pages WHERE document_id=?',(doc['id'],))
                c.executemany('INSERT INTO document_pages(document_id,page_no,text) VALUES(?,?,?)',[(doc['id'],n,text) for n,text in pages])
                c.execute('INSERT INTO company_document_index(document_id,page_count,char_count,indexed_at,error) VALUES(?,?,?,?,NULL) ON CONFLICT(document_id) DO UPDATE SET page_count=excluded.page_count,char_count=excluded.char_count,indexed_at=excluded.indexed_at,error=NULL',(doc['id'],len(pages),char_count,datetime.datetime.now(datetime.timezone.utc).isoformat()))
            indexed+=1
        except Exception as e:
            detail=str(e)[:400]; errors.append({'title':doc['title'],'error':detail})
            with connect() as c: c.execute('INSERT INTO company_document_index(document_id,page_count,char_count,indexed_at,error) VALUES(?,0,0,?,?) ON CONFLICT(document_id) DO UPDATE SET indexed_at=excluded.indexed_at,error=excluded.error',(doc['id'],datetime.datetime.now(datetime.timezone.utc).isoformat(),detail))
    with connect() as c: c.execute('INSERT INTO sync_log(source,status,records,detail,created_at) VALUES(?,?,?,?,?)',('Primary document extraction','partial' if errors else 'ok',indexed,f'{ticker}: {indexed} documents indexed; {len(errors)} errors.',datetime.datetime.now(datetime.timezone.utc).isoformat()))
    return {'ticker':ticker,'indexed':indexed,'errors':errors,'documents':rows('''SELECT d.*,i.page_count,i.char_count,i.indexed_at,i.error FROM company_documents d LEFT JOIN company_document_index i ON i.document_id=d.id WHERE d.ticker=? ORDER BY d.kind,d.title''',(ticker,))}

def search_primary_sources(ticker,question,limit=8):
    stop={'about','after','against','and','are','can','company','does','from','how','into','its','latest','more','most','over','show','that','the','their','this','through','what','when','where','which','with','would'}
    terms=list(dict.fromkeys(w.lower() for w in re.findall(r'[A-Za-z0-9.%+-]{2,}',question) if w.lower() not in stop))
    if not terms: raise ValueError('Add a specific topic such as revenue, cash flow, debt, guidance, or margins')
    records=rows('''SELECT d.title,d.kind,d.url,d.id,p.page_no,p.text FROM document_pages p
        JOIN company_documents d ON d.id=p.document_id JOIN company_document_index i ON i.document_id=d.id
        WHERE d.ticker=? AND i.error IS NULL ORDER BY d.discovered_at DESC,p.page_no''',(ticker.upper(),))
    hits=[]
    for record in records:
        sentences=re.split(r'(?<=[.!?])\s+|(?<=\n)|\s{2,}',record['text'])
        for sentence in sentences:
            clean=' '.join(sentence.split())
            if len(clean)<30: continue
            lower=clean.lower(); score=sum(1+(0.5 if lower.count(term)>1 else 0) for term in terms if term in lower)
            if score:
                hits.append({'title':record['title'],'kind':record['kind'],'url':record['url'],'page':record['page_no'],'score':round(score,1),'text':clean[:700]})
    hits.sort(key=lambda item:(-item['score'],item['title'],item['page']))
    unique=[]; seen=set()
    for item in hits:
        key=(item['title'],item['page'],item['text'][:120])
        if key not in seen: unique.append(item); seen.add(key)
        if len(unique)>=limit: break
    return {'ticker':ticker.upper(),'question':question,'matches':unique,'method':'Exact keyword retrieval from indexed annual reports, results filings, and earnings-call documents. No secondary research or model-generated claims are used.','notice':'Treat passages as evidence to review. FINN does not infer values, periods, or guidance that the source text does not state.'}

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
            return self.send_json({'companies':rows('SELECT * FROM companies WHERE active=1 ORDER BY name'),'events':events_with_network(),'people':network_profiles(),'preferences':prefs,'market_data':market,'read_only':READ_ONLY,'last_nse_sync':last_sync[0] if last_sync else None,'last_price_sync':last_price_sync[0] if last_price_sync else None,'source_mode':'NSE announcements and Yahoo Finance EOD prices are synced on demand; quotes are fetched on request'})
        if path=='/api/companies': return self.send_json(rows('SELECT * FROM companies ORDER BY name'))
        if path=='/api/events': return self.send_json(events_with_network())
        if path=='/api/sync/status': return self.send_json(rows('SELECT * FROM sync_log ORDER BY id DESC LIMIT 20'))
        if path=='/api/network':
            term=' '.join(q.get('q',[''])[0].split()).lower()
            ps=network_profiles()
            return self.send_json([p for p in ps if not term or term in ' '.join(str(v) for v in p.values()).lower()])
        if path.startswith('/api/quote/'):
            raw=path.rsplit('/',1)[-1].upper(); exchange='BO' if raw.endswith('.BO') else 'NS'; ticker=re.sub('[^A-Z0-9]','',raw.removesuffix('.NS').removesuffix('.BO'))
            if exchange=='BO':
                try:
                    quote=yahoo_quote(ticker,'BO'); quote['provider']='Yahoo Finance (BSE)'; return self.send_json(quote)
                except Exception as error: return self.send_json({'ticker':ticker,'error':str(error),'hint':'Yahoo Finance did not return a BSE quote.'},502)
            try: return self.send_json(nse_quote(ticker))
            except Exception as primary_error:
                try:
                    quote=yahoo_quote(ticker); quote['provider']='Yahoo Finance (NSE fallback)'; quote['primary_error']=str(primary_error); return self.send_json(quote)
                except Exception as fallback_error: return self.send_json({'ticker':ticker,'error':str(fallback_error),'primary_error':str(primary_error),'hint':'The NSE quote endpoint and Yahoo fallback are unavailable.'},502)
        if path.startswith('/api/sources/'):
            ticker=path.rsplit('/',1)[-1].upper(); return self.send_json(rows('SELECT * FROM sources WHERE ticker=? ORDER BY id DESC',(ticker,)))
        if path.startswith('/api/research/'):
            ticker=re.sub('[^A-Z0-9]','',path.rsplit('/',1)[-1].upper()); docs=rows('''SELECT d.*,i.page_count,i.char_count,i.indexed_at,i.error FROM company_documents d LEFT JOIN company_document_index i ON i.document_id=d.id WHERE d.ticker=? ORDER BY d.kind,d.title''',(ticker,)); return self.send_json({'ticker':ticker,'sources':rows('SELECT * FROM sources WHERE ticker=?',(ticker,)),'documents':docs,'notes':rows('SELECT * FROM research_notes WHERE ticker=? ORDER BY id DESC',(ticker,)),'notice':'Documents are discovered through Screener links and indexed as source text. Verify the original issuer or exchange document before relying on a claim.'})
        return super().do_GET()
    def do_POST(self):
        p=urlparse(self.path).path; b=self.body()
        allowed_sync=READ_ONLY and (p in ('/api/sync/nse','/api/sync/prices','/api/research/ask') or bool(re.fullmatch(r'/api/sync/company/[A-Z0-9.]+|/api/research/index/[A-Z0-9.]+',p)))
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
            m=re.fullmatch(r'/api/research/index/([A-Z0-9.]+)',p)
            if m:
                try: return self.send_json(index_company_documents(m.group(1)))
                except Exception as e: return self.send_json({'error':str(e)},400)
            if p=='/api/research/ask':
                ticker=re.sub('[^A-Z0-9]','',str(b.get('ticker','')).upper()); question=' '.join(str(b.get('question','')).split())
                if not ticker or not question: return self.send_json({'error':'ticker and question are required'},400)
                try: return self.send_json(search_primary_sources(ticker,question))
                except ValueError as e: return self.send_json({'error':str(e)},400)
            if p=='/api/events':
                required=['ticker','category','priority','title','summary']
                if any(not str(b.get(k,'')).strip() for k in required): return self.send_json({'error':'ticker, category, priority, title and summary are required'},400)
                with connect() as c:
                    cur=c.execute('INSERT INTO events(ticker,category,priority,title,summary,occurred,source,created_at) VALUES(?,?,?,?,?,?,?,?)',(b['ticker'].upper(),b['category'],b['priority'],b['title'],b['summary'],b.get('occurred','09:45'),b.get('source','User supplied'),datetime.datetime.now(datetime.timezone.utc).isoformat())); row=dict(c.execute('SELECT * FROM events WHERE id=?',(cur.lastrowid,)).fetchone())
                row['network_context']=network_context(row['ticker'],row['category']+' '+row['title']+' '+row['summary'])
                return self.send_json(row,201)
            if p=='/api/network':
                with connect() as c:
                    cur=c.execute('INSERT INTO people(name,initials,role,sectors,context,synthetic) VALUES(?,?,?,?,?,?)',(b['name'],b.get('initials',''.join(x[0] for x in b['name'].split()[:2]).upper()),b.get('role',''),b.get('sectors',''),b.get('context','User added profile'),int(bool(b.get('synthetic',False))))); row=dict(c.execute('SELECT * FROM people WHERE id=?',(cur.lastrowid,)).fetchone())
                row['tags']=PROFILE_TAGS.get(row['name'],[])
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
