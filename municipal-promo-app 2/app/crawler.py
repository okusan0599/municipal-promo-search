from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse, urldefrag

import requests
from bs4 import BeautifulSoup

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_FILE = DATA_DIR / "projects.json"
STATUS_FILE = DATA_DIR / "status.json"
CURSOR_FILE = DATA_DIR / "crawl_cursor.json"
SOURCES_FILE = BASE_DIR / "sources.json"

HEADERS = {"User-Agent": "MunicipalPromotionSearch/2.0 (public procurement index; contact: site administrator)", "Accept-Language": "ja,en;q=0.7"}
TIMEOUT = int(os.getenv("CRAWL_TIMEOUT", "18"))
REQUEST_INTERVAL = float(os.getenv("CRAWL_INTERVAL_SECONDS", "0.8"))
BATCH_SIZE = int(os.getenv("CRAWL_BATCH_SIZE", "20"))
MAX_HUBS = int(os.getenv("CRAWL_MAX_HUBS", "8"))
MAX_CANDIDATES = int(os.getenv("CRAWL_MAX_CANDIDATES", "60"))

CREATIVE_TERMS = ["プロモーション","広報","広告","観光","誘客","情報発信","魅力発信","PR","ＰＲ","SNS","ＳＮＳ","動画","映像","Web","WEB","ウェブ","ホームページ","サイト制作","イベント","キャンペーン","ブランディング","デザイン","クリエイティブ","メディア","移住","交流人口","関係人口","シティプロモーション","パンフレット","冊子","ロゴ","ポスター","広報誌","マーケティング"]
PROCUREMENT_TERMS = ["プロポーザル","企画提案","提案競技","公募","委託","入札","募集","業務"]
HUB_TERMS = ["入札","契約","調達","公募","プロポーザル","企画提案","委託","事業者募集","新着情報","募集情報"]
SKIP_TERMS = ["選定結果","審査結果","落札結果","契約結果","募集終了","受付終了","中止","過去の"]
FILE_EXTENSIONS = (".pdf",".doc",".docx",".xls",".xlsx",".zip",".ppt",".pptx")
THEME_RULES={"観光PR":["観光","誘客","周遊","旅行"],"広報・広告":["広報","広告","PR","ＰＲ","情報発信","魅力発信"],"SNS運用":["SNS","ＳＮＳ","ソーシャル"],"動画制作":["動画","映像","YouTube","ユーチューブ"],"Web制作":["Web","WEB","ウェブ","ホームページ","サイト制作"],"イベント":["イベント","催事","フェア","キャンペーン"],"ブランディング":["ブランド","ブランディング","ロゴ","デザイン"],"移住・関係人口":["移住","交流人口","関係人口"],"メディア":["メディア","テレビ","ラジオ","新聞","雑誌"]}
ERA_BASE={"令和":2018,"平成":1988}
SESSION=requests.Session(); SESSION.headers.update(HEADERS)

def read_json(path:Path,fallback):
    try:return json.loads(path.read_text(encoding="utf-8"))
    except Exception:return fallback

def write_json(path:Path,value):
    path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding="utf-8")

def fetch(url:str)->str:
    response=SESSION.get(url,timeout=TIMEOUT,allow_redirects=True); response.raise_for_status(); response.encoding=response.apparent_encoding or response.encoding; time.sleep(REQUEST_INTERVAL); return response.text

def compact(text:str)->str:return re.sub(r"\s+"," ",text).strip()
def normalize_url(url:str)->str:return urldefrag(url)[0]
def same_domain(a:str,b:str)->bool:
    x=urlparse(a).netloc.lower().split(':')[0].removeprefix('www.'); y=urlparse(b).netloc.lower().split(':')[0].removeprefix('www.')
    return x==y or x.endswith('.'+y) or y.endswith('.'+x)
def iso_date(y:int,m:int,d:int):
    try:return date(y,m,d).isoformat()
    except ValueError:return None
def parse_date(text:str):
    text=text.replace("元年","1年")
    for p in [r"(?P<era>令和|平成)\s*(?P<ey>\d{1,2})\s*年\s*(?P<m>\d{1,2})\s*月\s*(?P<d>\d{1,2})\s*日",r"(?P<y>20\d{2})\s*[年/.-]\s*(?P<m>\d{1,2})\s*[月/.-]\s*(?P<d>\d{1,2})\s*日?"]:
        m=re.search(p,text)
        if m:
            g=m.groupdict(); y=int(g['y']) if g.get('y') else ERA_BASE[g['era']]+int(g['ey']); return iso_date(y,int(g['m']),int(g['d']))
    return None
def date_near(text,labels):
    for label in labels:
        for m in re.finditer(label,text,re.I):
            value=parse_date(text[m.start():m.start()+220])
            if value:return value
    return None
def extract_notice(soup,text):
    for sel in ["time","[datetime]",".update",".date",".published",".last-modified"]:
        for n in soup.select(sel):
            v=parse_date(n.get('datetime') or n.get_text(' ',strip=True))
            if v:return v
    return date_near(text,["更新日","掲載日","公告日","公示日","公開日"])
def extract_deadline(text):return date_near(text,["企画提案書.*?提出期限","提案書.*?提出期限","応募書類.*?提出期限","提出期限","受領期限","受付期限","参加表明書.*?期限","参加申込.*?期限","応募期限","提出締切"])
def extract_presentation(text):return date_near(text,["プレゼンテーション","プレゼン","ヒアリング","審査会","提案審査"])
def extract_budget(text):
    for label in ["予算限度額","委託上限額","契約上限額","委託金額","提案上限額","予定価格","限度額","予算額"]:
        m=re.search(label+r".{0,120}",text,re.I)
        if m:
            a=re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(億円|万円|千円|円)",m.group(0).replace(',',''))
            if a:return round(float(a.group(1))*{"億円":10000,"万円":1,"千円":.1,"円":.0001}[a.group(2)],1)
    return None
def themes(text):return [k for k,ws in THEME_RULES.items() if any(w.lower() in text.lower() for w in ws)] or ["その他クリエイティブ"]
def candidate(text):
    low=text.lower(); return any(x.lower() in low for x in CREATIVE_TERMS) and any(x.lower() in low for x in PROCUREMENT_TERMS)
def links_from(html,base):
    soup=BeautifulSoup(html,'html.parser'); result=[]
    for a in soup.find_all('a',href=True):
        label=compact(a.get_text(' ',strip=True) or a.get('title','')); url=normalize_url(urljoin(base,a['href']))
        if label and url.startswith('http') and same_domain(base,url): result.append((label,url))
    return result

def discover_hubs(source):
    html=fetch(source['url']); scored=[]
    for label,url in links_from(html,source['url']):
        if url.lower().endswith(FILE_EXTENSIONS):continue
        score=sum(1 for t in HUB_TERMS if t.lower() in (label+' '+url).lower())
        if score:scored.append((score,label,url))
    scored.sort(key=lambda x:(-x[0],len(x[2])))
    seen=set(); hubs=[source['url']]
    for _,_,url in scored:
        if url not in seen and url!=source['url']:
            hubs.append(url);seen.add(url)
        if len(hubs)>=MAX_HUBS:break
    return hubs

def collect_candidates(source):
    found=[];seen=set()
    for hub in discover_hubs(source):
        try:html=fetch(hub)
        except Exception:continue
        for label,url in links_from(html,hub):
            if url in seen or url.lower().endswith(FILE_EXTENSIONS):continue
            if candidate(label+' '+url):
                found.append((label,url));seen.add(url)
                if len(found)>=MAX_CANDIDATES:return found
    return found

def parse_project(source,hinted,url):
    html=fetch(url); soup=BeautifulSoup(html,'html.parser')
    for tag in soup(['script','style','noscript','nav','footer']):tag.decompose()
    title_node=soup.find('h1') or soup.find('title'); title=compact(title_node.get_text(' ',strip=True)) if title_node else hinted
    text=compact(soup.get_text(' ',strip=True)); corpus=title+' '+text[:5000]
    if not candidate(corpus):return None
    deadline=extract_deadline(text); today=date.today().isoformat(); closed=any(t in corpus[:1600] for t in SKIP_TERMS)
    status='closed' if (deadline and deadline<today) or closed else ('soon' if deadline and (date.fromisoformat(deadline)-date.today()).days<=7 else 'open')
    return {'id':hashlib.sha1(url.encode()).hexdigest()[:16],'area':source['area'],'region':source['region'],'municipality':source['municipality'],'noticeDate':extract_notice(soup,text),'deadline':deadline,'presentationDate':extract_presentation(text),'budget':extract_budget(text),'theme':themes(corpus),'title':title,'summary':text[:360],'status':status,'sourceUrl':url,'sourceName':source['source_name'],'lastChecked':datetime.now().astimezone().isoformat(timespec='seconds')}

def crawl_all():
    DATA_DIR.mkdir(parents=True,exist_ok=True); sources=read_json(SOURCES_FILE,[]); old=read_json(DATA_FILE,[]); cursor=read_json(CURSOR_FILE,{'next_index':0}); start=int(cursor.get('next_index',0))%max(1,len(sources)); selected=[sources[(start+i)%len(sources)] for i in range(min(BATCH_SIZE,len(sources)))]
    status={'updated_at':datetime.now().astimezone().isoformat(timespec='seconds'),'state':'running','sources_total':len(sources),'batch_start':start,'batch_size':len(selected),'count':len(old),'processed':[],'errors':[]};write_json(STATUS_FILE,status)
    merged={p.get('sourceUrl'):p for p in old if p.get('sourceUrl')}
    for source in selected:
        record={'municipality':source['municipality'],'url':source['url'],'candidates':0,'saved':0,'status':'ok'}
        try:
            candidates=collect_candidates(source);record['candidates']=len(candidates)
            for hinted,url in candidates:
                try:
                    p=parse_project(source,hinted,url)
                    if p:merged[url]=p;record['saved']+=1
                except Exception as exc:status['errors'].append({'source':source['municipality'],'url':url,'error':str(exc)[:240]})
        except Exception as exc:record['status']='error';record['error']=str(exc)[:240];status['errors'].append({'source':source['municipality'],'error':str(exc)[:240]})
        status['processed'].append(record)
    results=sorted(merged.values(),key=lambda x:(x.get('status')=='closed',x.get('deadline') or '9999-12-31',x.get('noticeDate') or '0000-00-00'))
    write_json(DATA_FILE,results);next_index=(start+len(selected))%max(1,len(sources));write_json(CURSOR_FILE,{'next_index':next_index,'updated_at':datetime.now().astimezone().isoformat(timespec='seconds')});status.update({'updated_at':datetime.now().astimezone().isoformat(timespec='seconds'),'state':'completed','next_index':next_index,'count':len(results),'errors':status['errors'][-50:]});write_json(STATUS_FILE,status);return status
if __name__=='__main__':print(json.dumps(crawl_all(),ensure_ascii=False,indent=2))
