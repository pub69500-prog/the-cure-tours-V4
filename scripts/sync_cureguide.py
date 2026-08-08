#!/usr/bin/env python3
from __future__ import annotations
import datetime as dt, os, re, time, urllib.parse, urllib.request, urllib.robotparser
from bs4 import BeautifulSoup
from common import load, save, log_change, now, normalize
BASE='https://www.cure-concerts.de'
UA='STATICURE-archive-sync/4.0 (+https://github.com/pub69500-prog/the-cure-tours)'
TITLE_RE=re.compile(r'^(?P<artist>.*?)\s+(?P<date>\d{4}-(?:\d{2}|xx)-(?:\d{2}|xx))\s+(?P<city>.+?)\s+-\s+(?P<venue>.+?)\s+\((?P<country>[^)]+)\)')
LABELS={'Songs played':'songsPlayed','Set length':'setLengthMin','Set time':'setTime','Curfew':'curfew','Tour':'tour','Attendance':'attendance','Capacity':'concertCapacity','Address':'venueAddress'}

def allowed(url):
    respect=os.getenv('CUREGUIDE_RESPECT_ROBOTS','true').lower() not in {'0','false','no'}
    if not respect:return True
    rp=urllib.robotparser.RobotFileParser(BASE+'/robots.txt')
    try: rp.read(); return rp.can_fetch(UA,url)
    except Exception: return True

def fetch(url):
    if not allowed(url): raise RuntimeError(f'robots.txt interdit {url}')
    req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'text/html'})
    with urllib.request.urlopen(req,timeout=30) as r:return r.read().decode('utf-8','replace')

def candidates():
    year=dt.datetime.now().year
    pages=[f'{BASE}/main/updates.php',f'{BASE}/main/{year}.php',f'{BASE}/main/{year-1}.php']
    urls=set()
    for page in pages:
        try:
            soup=BeautifulSoup(fetch(page),'html.parser')
            for a in soup.find_all('a',href=True):
                u=urllib.parse.urljoin(page,a['href'])
                if re.search(r'/concerts/\d{4}-(?:\d{2}|xx)-(?:\d{2}|xx)\.php$',u): urls.add(u)
        except Exception as e: print('[cureguide]',page,e)
        time.sleep(.8)
    return sorted(urls)

def parse(url,html):
    soup=BeautifulSoup(html,'html.parser')
    title=(soup.title.get_text(' ',strip=True) if soup.title else '')
    text='\n'.join(x.strip() for x in soup.get_text('\n').splitlines() if x.strip())
    m=TITLE_RE.search(title) or TITLE_RE.search(text)
    date=re.search(r'(\d{4}-(?:\d{2}|xx)-(?:\d{2}|xx))',url).group(1)
    out={'id':None,'date':date,'year':int(date[:4]),'sourceUrl':url,'scrapedAt':now(),'pageTitle':title,'sources':{'primary':'cure-concerts.de'}}
    if m: out.update({'artist':m['artist'].strip() or 'The Cure','city':m['city'].strip(),'venue':m['venue'].strip(),'country':m['country'].strip()})
    lines=text.splitlines()
    for i,line in enumerate(lines):
        for label,key in LABELS.items():
            if line.rstrip(':').lower()==label.lower() and i+1<len(lines):
                val=lines[i+1]
                if key in {'songsPlayed','attendance','concertCapacity','setLengthMin'}:
                    n=re.search(r'[\d,]+',val)
                    if n: val=int(n.group(0).replace(',',''))
                out[key]=val
    # Event/festival appears frequently in title/text but is intentionally not guessed.
    return out

def main():
    concerts=load('concerts.json',[]); changes=load('changelog.json',[])
    byid={c['id']:c for c in concerts}
    byurl={c.get('sourceUrl'):c for c in concerts if c.get('sourceUrl')}
    urls=candidates(); print(f'[cureguide] {len(urls)} candidate pages')
    for n,url in enumerate(urls,1):
        try: patch=parse(url,fetch(url))
        except Exception as e: print('[cureguide] skip',url,e); continue
        old=byurl.get(url)
        if old is None:
            same=[c for c in byid.values() if c.get('date')==patch['date'] and normalize(c.get('city'))==normalize(patch.get('city')) and normalize(c.get('venue'))==normalize(patch.get('venue'))]
            old=same[0] if len(same)==1 else None
        if old is None:
            base=f"cureguide:{patch['date']}:{normalize(patch.get('city')).replace(' ','-')}:{normalize(patch.get('venue')).replace(' ','-')}".rstrip(':')
            cid=base; ndup=2
            while cid in byid: cid=f'{base}:{ndup}'; ndup+=1
            patch['id']=cid; byid[cid]=patch; byurl[url]=patch; log_change(changes,cid,patch['date'],'event',None,'created',url,'NEW_EVENT')
        else:
            for k,v in patch.items():
                if k in {'id','sources'} or v in (None,''): continue
                if k=='scrapedAt': old[k]=v; continue
                if old.get(k)!=v:
                    log_change(changes,old['id'],old['date'],k,old.get(k),v,url,'HISTORICAL_CORRECTION' if old['year']<dt.datetime.now().year else 'UPDATED_EVENT')
                    old[k]=v
            old.setdefault('sources',{})['primary']='cure-concerts.de'
        if n%10==0: print(f'[cureguide] {n}/{len(urls)}')
        time.sleep(.8)
    save('concerts.json',sorted(byid.values(),key=lambda c:c['date']))
    save('changelog.json',changes[-5000:])
    state=load('state.json',{}); state['cureGuideLastSync']=now(); state['cureGuideCandidates']=len(urls); save('state.json',state)
if __name__=='__main__': main()
