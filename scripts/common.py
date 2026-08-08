from __future__ import annotations
import datetime as dt, json, re, unicodedata
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data'

def load(name, default):
    p=DATA/name
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else default

def save(name,obj):
    (DATA/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n",encoding='utf-8')

def normalize(v):
    if v is None:return ''
    s=unicodedata.normalize('NFKD',str(v)); s=''.join(c for c in s if not unicodedata.combining(c))
    return re.sub(r'\s+',' ',re.sub(r'[^a-z0-9]+',' ',s.lower())).strip()

def now(): return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()

def log_change(changes, cid, date, field, old, new, source, kind):
    if old==new:return
    changes.append({'timestamp':now(),'concertId':cid,'date':date,'field':field,'old':old,'new':new,'source':source,'type':kind})
