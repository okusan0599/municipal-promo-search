from __future__ import annotations
import hashlib, json, re, sqlite3, sys
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
from dateutil import parser as dtparser

ROOT=Path(__file__).resolve().parents[1]
DB=ROOT/'data'/'projects.db'; OUT=ROOT/'data'/'projects.json'; SOURCES=ROOT/'sources.json'
UA='MunicipalPromoCrawler/1.0 (+public procurement research; low frequency)'
KEYWORDS=['プロモーション','広報','広告','観光','誘客','SNS','動画','映像','Web','ウェブ','サイト制作','イベント','ブランディング','情報発信','クリエイティブ','キャンペーン','PR','デザイン','ロゴ','コンテンツ','企画運営']
PROC=['プロポーザル','企画提案','提案競技','企画コンペ','公募','委託']
EXCLUDE=['審査結果','選定結果','契約結果','委託先を決定','質問と回答','質問への回答','募集終了','中止']
THEMES={'観光PR':['観光','誘客','インバウンド'],'SNS運用':['SNS','Instagram','X（旧Twitter）','LINE'],'動画制作':['動画','映像','CM'],'イベント':['イベント','催事','フェスタ','大会'],'Web制作':['Web','ウェブ','ホームページ','サイト'],'広告':['広告','メディア','交通広告'],'ブランディング':['ブランド','ブランディング','ロゴ'],'移住促進':['移住','定住'],'文化発信':['文化','芸術','アート'],'広報':['広報','情報発信','PR']}

def txt(node): return ' '.join(node.get_text(' ',strip=True).split())
def iso_from(s):
    pats=[r'(20\d{2})[年/.-]\s*(\d{1,2})[月/.-]\s*(\d{1,2})日?',r'令和\s*(\d{1,2})年\s*(\d{1,2})月\s*(\d{1,2})日']
    for i,p in enumerate(pats):
        m=re.search(p,s)
        if m:
            y=int(m.group(1))+(2018 if i else 0); mo=int(m.group(2)); d=int(m.group(3))
            try:return date(y,mo,d).isoformat()
            except:return None
    return None

def deadline_from(text, base_year):
    candidates=[]
    for m in re.finditer(r'(?:提出|提案書|参加申込|申請|応募|締切|期限)[^。\n]{0,35}?(20\d{2})年\s*(\d{1,2})月\s*(\d{1,2})日',text):
        try:candidates.append(date(int(m.group(1)),int(m.group(2)),int(m.group(3))))
        except:pass
    for m in re.finditer(r'(?:提出|提案書|参加申込|申請|応募|締切|期限)[^。\n]{0,25}?(\d{1,2})月\s*(\d{1,2})日',text):
        try:candidates.append(date(base_year,int(m.group(1)),int(m.group(2))))
        except:pass
    return max(candidates).isoformat() if candidates else None

def budget_from(text):
    pats=[(r'(?:上限|限度|予算|委託料|契約金額)[^\n。]{0,30}?([\d,]+(?:\.\d+)?)\s*万円',10000),(r'(?:上限|限度|予算|委託料|契約金額)[^\n。]{0,30}?([\d,]+)\s*千円',1000),(r'(?:上限|限度|予算|委託料|契約金額)[^\n。]{0,30}?([\d,]+)\s*円',1)]
    for p,mul in pats:
        m=re.search(p,text)
        if m:
            return round(float(m.group(1).replace(',',''))*mul/10000)
    return None

def classify(text):
    found=[k for k,ws in THEMES.items() if any(w.lower() in text.lower() for w in ws)]
    return found[:4] or ['その他クリエイティブ']

def fetch(url):
    r=requests.get(url,headers={'User-Agent':UA},timeout=30); r.raise_for_status(); r.encoding=r.apparent_encoding or r.encoding
    return r.text

def ensure_db():
    DB.parent.mkdir(exist_ok=True)
    con=sqlite3.connect(DB)
    con.execute('''CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY, area TEXT, region TEXT, municipality TEXT, notice_date TEXT, deadline TEXT, presentation_date TEXT, budget INTEGER, themes TEXT, title TEXT, summary TEXT, status TEXT, source_url TEXT, source_name TEXT, last_checked TEXT, confidence REAL)''')
    return con

def crawl_source(src):
    html=fetch(src['url']); soup=BeautifulSoup(html,'html.parser'); found=[]
    for a in soup.find_all('a',href=True):
        title=txt(a)
        if len(title)<8 or not any(k.lower() in title.lower() for k in PROC) or not any(k.lower() in title.lower() for k in KEYWORDS): continue
        if any(x in title for x in EXCLUDE): continue
        url=urljoin(src['url'],a['href'])
        if urlparse(url).netloc!=urlparse(src['url']).netloc: continue
        context=txt(a.parent)[:500]
        notice=iso_from(context) or iso_from(title)
        detail=''
        try: detail=txt(BeautifulSoup(fetch(url),'html.parser'))[:120000]
        except Exception: detail=context
        combined=title+' '+detail
        base_year=int((notice or date.today().isoformat())[:4])
        deadline=deadline_from(combined,base_year)
        budget=budget_from(combined)
        status='open'
        if any(x in combined[:5000] for x in ['募集終了','受付終了','公募終了','中止']): status='closed'
        elif deadline:
            dd=date.fromisoformat(deadline)
            if dd<date.today(): status='closed'
            elif dd<=date.today()+timedelta(days=7): status='soon'
        pid=hashlib.sha256(url.encode()).hexdigest()[:20]
        summary=re.sub(r'\s+',' ',detail)[:240] if detail else title
        found.append({'id':pid,'area':src['area'],'region':src['region'],'municipality':src['municipality'],'noticeDate':notice,'deadline':deadline,'presentationDate':None,'budget':budget,'theme':classify(combined),'title':title,'summary':summary,'status':status,'sourceUrl':url,'sourceName':src['name'],'lastChecked':datetime.now().astimezone().isoformat(timespec='minutes'),'confidence':0.72 if deadline else 0.55})
    return found

def main():
    sources=json.loads(SOURCES.read_text())
    allp=[]; errors=[]
    for s in sources:
        try: allp.extend(crawl_source(s))
        except Exception as e: errors.append({'source':s['name'],'error':str(e)})
    con=ensure_db()
    for p in allp:
        con.execute('''INSERT INTO projects VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET area=excluded.area,region=excluded.region,municipality=excluded.municipality,notice_date=excluded.notice_date,deadline=excluded.deadline,presentation_date=excluded.presentation_date,budget=excluded.budget,themes=excluded.themes,title=excluded.title,summary=excluded.summary,status=excluded.status,source_url=excluded.source_url,source_name=excluded.source_name,last_checked=excluded.last_checked,confidence=excluded.confidence''',(p['id'],p['area'],p['region'],p['municipality'],p['noticeDate'],p['deadline'],p['presentationDate'],p['budget'],json.dumps(p['theme'],ensure_ascii=False),p['title'],p['summary'],p['status'],p['sourceUrl'],p['sourceName'],p['lastChecked'],p['confidence']))
    con.commit()
    rows=con.execute('SELECT * FROM projects ORDER BY COALESCE(deadline,"9999-12-31"), COALESCE(notice_date,"0000-00-00") DESC').fetchall(); cols=[d[0] for d in con.execute('SELECT * FROM projects LIMIT 0').description]
    out=[]
    for r in rows:
        x=dict(zip(cols,r)); out.append({'id':x['id'],'area':x['area'],'region':x['region'],'municipality':x['municipality'],'noticeDate':x['notice_date'],'deadline':x['deadline'],'presentationDate':x['presentation_date'],'budget':x['budget'],'theme':json.loads(x['themes']),'title':x['title'],'summary':x['summary'],'status':x['status'],'sourceUrl':x['source_url'],'sourceName':x['source_name'],'lastChecked':x['last_checked'],'confidence':x['confidence']})
    OUT.write_text(json.dumps({'generatedAt':datetime.now().astimezone().isoformat(timespec='minutes'),'projects':out,'errors':errors},ensure_ascii=False,indent=2))
    print(json.dumps({'projects':len(out),'new_or_updated':len(allp),'errors':errors},ensure_ascii=False))
if __name__=='__main__': main()
