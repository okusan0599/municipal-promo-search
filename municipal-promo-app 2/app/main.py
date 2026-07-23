from __future__ import annotations
import json, os, threading, time
from datetime import datetime, timedelta
from pathlib import Path
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from .crawler import DATA_FILE, STATUS_FILE, SOURCES_FILE, crawl_all
BASE_DIR=Path(__file__).resolve().parent.parent; INDEX_FILE=BASE_DIR/'index.html'; DATA_DIR=BASE_DIR/'data'
app=FastAPI(title='Municipal Promotion Search - Stage 1')
_refresh_lock=threading.Lock()
def read_json(path,fallback):
    try:return json.loads(path.read_text(encoding='utf-8'))
    except Exception:return fallback
def is_stale(hours=6):
    raw=read_json(STATUS_FILE,{}).get('updated_at')
    if not raw:return True
    try:
        u=datetime.fromisoformat(raw);return datetime.now(u.tzinfo)-u>timedelta(hours=hours)
    except Exception:return True
def refresh_safely():
    if not _refresh_lock.acquire(blocking=False):return
    try:crawl_all()
    finally:_refresh_lock.release()
def scheduler():
    interval=max(1,int(os.getenv('REFRESH_INTERVAL_HOURS','6')))*3600
    while True:
        time.sleep(interval)
        if os.getenv('AUTO_REFRESH','true').lower()=='true':refresh_safely()
@app.on_event('startup')
def startup():
    if os.getenv('AUTO_REFRESH','true').lower()=='true' and is_stale():threading.Thread(target=refresh_safely,daemon=True).start()
    threading.Thread(target=scheduler,daemon=True).start()
@app.get('/health')
def health():return {'status':'ok'}
@app.get('/api/projects')
def projects():return JSONResponse(content=read_json(DATA_FILE,[]))
@app.get('/api/status')
def status():return JSONResponse(content=read_json(STATUS_FILE,{'updated_at':None,'state':'not_started','count':0,'errors':[]}))
@app.get('/api/sources')
def sources():return JSONResponse(content=read_json(SOURCES_FILE,[]))
@app.post('/api/refresh')
def refresh(background_tasks:BackgroundTasks,x_refresh_token:str|None=Header(default=None)):
    expected=os.getenv('REFRESH_TOKEN')
    if not expected:raise HTTPException(status_code=503,detail='REFRESH_TOKEN is not configured')
    if x_refresh_token!=expected:raise HTTPException(status_code=401,detail='Invalid refresh token')
    background_tasks.add_task(refresh_safely);return {'status':'refresh started'}
@app.get('/')
def index():return FileResponse(INDEX_FILE)
if DATA_DIR.exists():app.mount('/data',StaticFiles(directory=DATA_DIR),name='data')
