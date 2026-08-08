#!/usr/bin/env python3
from __future__ import annotations
import datetime as dt, json, os, time, urllib.parse, urllib.request
from common import load, save, normalize, log_change, now
API='https://api.setlist.fm/rest/1.0'; MBID='69ee3720-a7cb-4402-b48d-a02c366f2bcf'
def get(path,params,key):
    url=API+path+'?'+urllib.parse.urlencode(params)
    req=urllib.request.Request(url,headers={'Accept':'application/json','X-Api-Key':key,'User-Agent':'STATICURE/4.0'})
    with urllib.request.urlopen(req,timeout=30) as r:return json.loads(r.read())
def year_items(year,key):
    out=[]; p=1
    while True:
        d=get('/search/setlists',{'artistMbid':MBID,'year':year,'p':p},key); items=d.get('setlist') or []; out+=items
        if not items or p*int(d.get('itemsPerPage') or 20)>=int(d.get('total') or len(out)):break
        p+=1; time.sleep(.65)
    return out
def songs(item):
    out=[]
    for s in ((item.get('sets') or {}).get('set') or []):
        enc=s.get('encore'); section=f'Encore {enc}' if enc else 'Mainset'; pos=0
        for song in s.get('song') or []:
            if song.get('tape'):continue
            name=(song.get('name') or '').strip()
            if name: pos+=1; out.append({'section':section,'position':pos,'song':name})
    return out
def main():
    key=os.getenv('SETLISTFM_API_KEY','').strip()
    if not key: print('[setlist.fm] no key; skipped'); return
    concerts=load('concerts.json',[]); sl=load('setlists.json',[]); changes=load('changelog.json',[])
    bydate={c['date']:c for c in concerts}; current=dt.datetime.now().year
    for year in (current-1,current):
        for item in year_items(year,key):
            d=dt.datetime.strptime(item['eventDate'],'%d-%m-%Y').date().isoformat(); venue=item.get('venue') or {}; city=venue.get('city') or {}; country=city.get('country') or {}
            c=bydate.get(d)
            if c is None:
                c={'id':f'setlistfm:{item.get("id") or d}','date':d,'year':year,'artist':'The Cure','eventType':'Concert','city':city.get('name'),'venue':venue.get('name'),'country':country.get('name'),'sources':{'secondary':'setlist.fm'}}
                concerts.append(c); bydate[d]=c; log_change(changes,c['id'],d,'event',None,'created','setlist.fm','NEW_EVENT')
            c.setdefault('sources',{})['secondary']='setlist.fm'; c['setlistFmUrl']=item.get('url'); c['setlistFmId']=item.get('id')
            # Primary Cure Guide location wins; setlist.fm fills blanks only.
            for k,v in [('city',city.get('name')),('venue',venue.get('name')),('country',country.get('name')),('tour',(item.get('tour') or {}).get('name'))]:
                if not c.get(k) and v: c[k]=v
            news=songs(item)
            if news:
                existing=[x for x in sl if x.get('concertId')==c['id'] or x.get('date')==d]
                # Only replace recent setlist if missing, unconfirmed, or source is setlist.fm.
                if not existing or str(c.get('setlistStatus') or '').lower() in {'','unknown','unconfirmed'}:
                    sl=[x for x in sl if not (x.get('concertId')==c['id'] or x.get('date')==d)]
                    sl += [{'concertId':c['id'],'date':d,**x,'countsAsSong':True,'status':'Community','sourceUrl':item.get('url')} for x in news]
                    c['songsPlayed']=len(news); c['setlistStatus']=c.get('setlistStatus') or 'Community'
                    log_change(changes,c['id'],d,'setlist',len(existing),len(news),item.get('url') or 'setlist.fm','NEW_SETLIST')
        time.sleep(.65)
    save('concerts.json',sorted(concerts,key=lambda x:x['date'])); save('setlists.json',sl); save('changelog.json',changes[-5000:])
    state=load('state.json',{}); state['setlistFmLastSync']=now(); save('state.json',state)
if __name__=='__main__': main()
