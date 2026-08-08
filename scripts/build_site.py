#!/usr/bin/env python3
from __future__ import annotations
import json, shutil, datetime as dt
from collections import Counter
from pathlib import Path
from common import ROOT, DATA, load, save
DIST=ROOT/'dist'; SITE=ROOT/'site'
def main():
    concerts=load('concerts.json',[]); setlists=load('setlists.json',[]); changes=load('changelog.json',[]); state=load('state.json',{})
    if DIST.exists(): shutil.rmtree(DIST)
    shutil.copytree(SITE,DIST)
    (DIST/'data').mkdir(exist_ok=True)
    for name in ('concerts.json','setlists.json','changelog.json','state.json'):
        shutil.copy2(DATA/name,DIST/'data'/name)
    years=Counter(c.get('year') for c in concerts); countries=Counter(c.get('country') for c in concerts if c.get('country')); venues=Counter(c.get('venue') for c in concerts if c.get('venue'))
    songs=Counter(x.get('song') for x in setlists if x.get('countsAsSong',True) and x.get('song') and not str(x.get('song')).startswith('['))
    stats={'concerts':len(concerts),'setlistEntries':len(setlists),'years':dict(sorted(years.items())),'countries':countries.most_common(30),'venues':venues.most_common(30),'songs':songs.most_common(100),'generatedAt':dt.datetime.now(dt.timezone.utc).isoformat(),'lastSync':state.get('lastSync') or state.get('cureGuideLastSync')}
    (DIST/'data'/'stats.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2),encoding='utf-8')
    print('[build] dist ready:',len(concerts),'concerts')
if __name__=='__main__': main()
