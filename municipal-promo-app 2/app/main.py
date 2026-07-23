from pathlib import Path
import json, sqlite3
from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
ROOT=Path(__file__).resolve().parents[1]; DB=ROOT/'data'/'projects.db'
app=FastAPI(title='自治体プロモーション公示API')
@app.get('/api/projects')
def projects(area:str|None=None,region:str|None=None,budget_min:int|None=None,budget_max:int|None=None,status:str|None=None,q:str|None=None):
    con=sqlite3.connect(DB); con.row_factory=sqlite3.Row
    sql='SELECT * FROM projects WHERE 1=1'; args=[]
    for col,val in [('area',area),('region',region),('status',status)]:
        if val: sql+=f' AND {col}=?'; args.append(val)
    if budget_min is not None: sql+=' AND budget>=?'; args.append(budget_min)
    if budget_max is not None: sql+=' AND budget<=?'; args.append(budget_max)
    if q: sql+=' AND (title LIKE ? OR summary LIKE ?)'; args += [f'%{q}%',f'%{q}%']
    rows=con.execute(sql+' ORDER BY COALESCE(deadline,"9999-12-31")',args).fetchall()
    return [dict(r)|{'theme':json.loads(r['themes']),'noticeDate':r['notice_date'],'presentationDate':r['presentation_date'],'sourceUrl':r['source_url'],'sourceName':r['source_name'],'lastChecked':r['last_checked']} for r in rows]
@app.get('/api/health')
def health(): return {'ok':True}
@app.get('/')
def index(): return FileResponse(ROOT/'index.html')
app.mount('/data',StaticFiles(directory=ROOT/'data'),name='data')
