#!/usr/bin/env python3
"""Respectful weekly collector for official European power-electronics training pages.

The seven 'structured' sources are parsed conservatively; other sources are
change-monitored only. No guessed dates, prices, or registrations are published.
If a source fails, its previous verified courses remain (until expiration).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
HEADERS = {'User-Agent': 'PETrainingRadar/1.0 (+https://github.com/wgchen25-droid/petraining; weekly public training metadata only)', 'Accept-Language': 'en,de;q=0.9'}
MONTHS = {'jan': 1, 'january': 1, 'januar': 1, 'feb': 2, 'february': 2, 'februar': 2, 'mär': 3, 'märz': 3,
          'mar': 3, 'march': 3, 'mrz': 3, 'apr': 4, 'april': 4, 'may': 5, 'mai': 5, 'jun': 6, 'june': 6, 'juni': 6,
          'jul': 7, 'july': 7, 'juli': 7, 'aug': 8, 'august': 8, 'sep': 9, 'sept': 9, 'september': 9,
          'okt': 10, 'oct': 10, 'october': 10, 'oktober': 10, 'nov': 11, 'november': 11,
          'dec': 12, 'december': 12, 'dez': 12, 'dezember': 12}
MONTH_RE = '|'.join(sorted(map(re.escape, MONTHS), key=len, reverse=True))
NUMDATE = r'(?<!\d)(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})(?!\d)'
EN_M = rf'(?:{MONTH_RE})\.?'
TECH = re.compile(r'power|elektroni|elektromobil|emv\b|emc\b|emi\b|inductor|magnetic|capacitor|converter|pfc\b|power supply|transformer|inverter|semiconductor|sic\b|gan\b|cooling|reliability|sensor|isolation|isolation coordination|schaltnetz|stromrichter|filter|regelung|hochvolt|lade|antrieb|model|simulat|wandler|digital control|sensing|packaging|thermal', re.I)
SKIP = re.compile(r'^(?:register|anmelden|programme?|details?|read more|watch|download|more information|contact|seminar program|all events|webinars?|upcoming|newsletter|home|select|search|overview|about us|news|calendar|registration|power electronics)$',re.I)
CITIES = ('Berlin', 'Bremen', 'Hamburg', 'Nuremberg', 'Nürnberg', 'Erlangen', 'Reutlingen', 'Delft', 'Prague', 'Lyon', 'Karlsruhe', 'Würzburg', 'Munich', 'München', 'Freiham', 'Essen', 'Ostfildern', 'Kassel', 'Stuttgart', 'Zürich', 'Zurich', 'Roma', 'Frascati', 'Hannover', 'Drammen', 'Sønderborg')
CATEGORY_RULES = [
    ('SiC / GaN', re.compile(r'\bsic\b|\bgan\b|wide.?bandgap', re.I)),
    ('EMC / EMI', re.compile(r'emc|emi|\bemv\b|electromagnetic|filter|parasitic|low.noise', re.I)),
    ('热管理与可靠性', re.compile(r'reliability|zuverlässig|lebensdauer|cooling|thermal|thermisch|isolat|lifetime|ausfall', re.I)),
    ('功率器件与封装', re.compile(r'semiconductor|halbleiter|packaging|sensor|characterisation|characterization|transistor|gate.driver|power module', re.I)),
    ('控制与仿真', re.compile(r'control|regelung|simulation|digital|modelling|modellbildung|plecs|loop|state.space|pfc', re.I)),
    ('电驱与新能源', re.compile(r'electro.?vehicle|e.?mobil|antrieb|charging|ladetech|battery|grid|pv.storage|inductive power', re.I)),
]


def normalize(s: str) -> str:
    return re.sub(r'\s+', ' ', s or '').strip()


def make_date(y: int, m: int, d: int) -> date | None:
    try:
        return date(y if y >= 100 else 2000 + y, m, d)
    except (ValueError, TypeError):
        return None


def parse_dates(s: str) -> tuple[str, str] | None:
    """Extract a proven date/range in German, EN or numeric format."""
    s = normalize(s)
    nums = list(re.finditer(NUMDATE, s))
    if nums:
        def to_date(m): return make_date(int(m[3]), int(m[2]), int(m[1]))
        a = to_date(nums[0])
        if a:
            b = to_date(nums[1]) if len(nums)>1 and nums[1].start()-nums[0].end() < 28 else a
            return a.isoformat(), (b or a).isoformat()
    # e.g. November 30th - December 3rd 2026 / May 31 - Jun 2, 2027
    p = re.search(rf'\b({EN_M})\s+(\d{{1,2}})(?:st|nd|rd|th)?\s*(?:,?\s*(\d{{4}})|\s*[-–—]\s*(?:({EN_M})\s+)?(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s*(\d{{4}}))?)', s, flags=re.I)
    if p:
        m1 = MONTHS.get(p[1].lower().rstrip('.'))
        year = int(p[3] or p[6] or date.today().year)
        a = make_date(year, m1, int(p[2])) if m1 else None
        m2 = MONTHS.get((p[4] or p[1]).lower().rstrip('.'))
        b = make_date(year, m2, int(p[5])) if p[5] and m2 else a
        if a:
            if b and b < a: b = make_date(year+1, m2, int(p[5]))
            return a.isoformat(), (b or a).isoformat()
    # German "10. März 2027" or "18. Feb 2027" or single "24. Nov. 2026"
    p = re.search(rf'(?<!\d)(\d{{1,2}})\.\s*({EN_M})\s*(\d{{4}})', s, re.I)
    if p:
        m = MONTHS.get(p[2].lower().rstrip('.'))
        a = make_date(int(p[3]), m, int(p[1])) if m else None
        if a: return a.isoformat(), a.isoformat()
    return None


def classify(title: str) -> str:
    for category, pattern in CATEGORY_RULES:
        if pattern.search(title): return category
    return '基础与设计'


def resolve_location(text: str, source_id: str) -> tuple[str, str, str]:
    """Country/city never inferred from the company's HQ for online events."""
    text = normalize(text)
    mode = '混合' if re.search(r'\bhybrid\b|\bmixed\b|präsenz/hybrid|/\s*online',text,re.I) else ('线上' if re.search(r'\bwebinar\b|\bonline\b|digital event|self.paced',text,re.I) else '线下')
    city = next((city for city in CITIES if re.search(r'(?<!\w)'+re.escape(city)+r'(?!\w)',text,re.I)), '')
    mapping = {'Delft':'荷兰','Lyon':'法国','Prague':'捷克','Zurich':'瑞士','Zürich':'瑞士','Roma':'意大利','Frascati':'意大利','Drammen':'挪威','Sønderborg':'丹麦'}
    country = mapping.get(city,'德国')
    if not city and mode == '线上': return 'Online', '欧洲/全球', '线上'
    if source_id == 'plexim' and not city: return '地点待确认','瑞士','线下'
    if not city and source_id == 'biricha': city = 'Munich'
    if not city: city = '地点待确认'
    return city, country, mode


def parsed_price(s: str, source_id: str):
    if source_id == 'wuerth': return 0  # official page explicitly states free webinars
    if source_id not in ('biricha','etech','ti','ecpe','cluster','plexim','ieee'): return None
    m = re.search(r'(?:€|EUR)\s*([\d,.]+)', s, re.I)
    if not m: return None
    val = m[1].strip('.,')
    if ',' in val and '.' in val: val = val.replace(',','') if val.rfind('.')>val.rfind(',') else val.replace('.','').replace(',','.')
    elif ',' in val: val = val.replace(',','.') if len(val.rsplit(',',1)[1])==2 else val.replace(',','')
    elif val.count('.') == 1 and len(val.rsplit('.',1)[1])==3: val=val.replace('.','')
    try:
        p=float(val)
        return int(p) if 0<=p<=20000 and p==int(p) else None
    except ValueError: return None


def build_event(source: dict, title: str, text: str, href: str) -> dict | None:
    title=normalize(title).strip(' -|•')
    if not 11<=len(title)<=150 or SKIP.match(title) or not TECH.search(title): return None
    dr=parse_dates(text)
    if not dr: return None
    a,b=dr
    start=date.fromisoformat(a)
    if not date.today()-timedelta(days=45)<=start<=date.today()+timedelta(days=730): return None
    if date.fromisoformat(b)<start or date.fromisoformat(b)>start+timedelta(days=14): b=a
    city,country,mode=resolve_location(text,source['id'])
    if source['id'] in ('wuerth','ti','ieee','etech'): city,country,mode=('Online','欧洲/全球','线上') if source['id'] in ('wuerth','ti','ieee') or re.search(r'webinar|online',text,re.I) else (city,country,mode)
    if source['id']=='biricha' and country!='德国': return None # European workshops only
    link=urljoin(source['url'],href) if href else source['url']
    if urlsplit(link).scheme not in ('https','http'): link=source['url']
    key=source['id']+'|'+title+'|'+a
    return dict(id=hashlib.sha1(key.encode()).hexdigest()[:12],source_id=source['id'],provider=source['name'],title=title,
                start_date=a,end_date=b,city=city,country=country,mode=mode,category=classify(title),language='英语' if source['id'] in ('ecpe','biricha','wuerth','ti','ieee','plexim') else '待确认',
                price_eur=parsed_price(text,source['id']),url=link,notes='',verified_at=date.today().isoformat(),origin='自动提取 · 官方网页')


def parse_structured_page(source: dict, html: str) -> list[dict]:
    soup=BeautifulSoup(html,'html.parser')
    for el in soup(['script','style','noscript','nav','footer']): el.decompose()
    items=[]
    # page types: event row with linked title, product/workshop card heading,
    # or event data grouped in table rows.
    candidates=[]
    for a in soup.find_all('a',href=True):
        t=normalize(a.get_text(' ',strip=True))
        if 11<=len(t)<=150 and TECH.search(t) and not SKIP.fullmatch(t): candidates.append((a,t,a.get('href','')))
    for h in soup.find_all(['h2','h3','h4','h5']):
        t=normalize(h.get_text(' ',strip=True))
        if 11<=len(t)<=150 and TECH.search(t) and not SKIP.fullmatch(t): candidates.append((h,t,''))
    seen=set()
    for node,title,href in candidates:
        # Pick the smallest relevant ancestor with a date. Large containers
        # spanning several unrelated events are not trusted.
        p=node
        for _ in range(6):
            p=p.parent
            if p is None or p.name in ('html','body'): break
            txt=normalize(p.get_text(' ',strip=True))
            if not (len(title)<=len(txt)<=950): continue
            if not parse_dates(txt): continue
            # The first dated row/card is preferred to prevent grabbing a
            # random date from the site's schedule header.
            ev=build_event(source,title,txt,href)
            if ev:
                key=ev['start_date']+'|'+re.sub(r'\W+','',ev['title']).lower()
                if key not in seen: items.append(ev);seen.add(key)
                break
    # Extract compact event lines on calendar tables that use plaintext rather
    # than titles wrapped in clickable anchors.
    if source['id'] in ('ecpe','cluster') and len(items)<3:
        txt=normalize(soup.get_text(' ',strip=True))
        pat=re.compile(r'(?P<title>[\wÀ-ÿ ,()–\-:/]+?)\s*\|\s*(?:ECPE|Cluster)[^|]{0,95}?(?:where\?|wo\?)\s*(?P<city>[^|]{1,65}?)\s*(?:when\?|wann\?)\s*(?P<dates>\d{1,2}[./]\d{1,2}[./]\d{4}\s*[-–]\s*\d{1,2}[./]\d{1,2}[./]\d{4})',re.I)
        for m in pat.finditer(txt):
            ev=build_event(source,m['title'],m.group(0),'')
            if ev and not any(x['title']==ev['title'] and x['start_date']==ev['start_date'] for x in items):items.append(ev)
    return items[:100]


def scan(sources: list[dict], previous: dict, *, dry_run=False, only=None):
    now=datetime.now(timezone.utc).isoformat(timespec='seconds')
    old=previous.get('courses',[])
    today=date.today()
    course_index={c['id']:dict(c) for c in old if c.get('end_date','9999-12-31')>=str(today-timedelta(days=60))}
    old_status=previous.get('source_status',{})
    statuses={k:dict(v) for k,v in old_status.items()}
    successes=0
    newest=0
    for source in sources:
        sid=source['id']
        if only and sid not in only: continue
        prior=old_status.get(sid,{})
        entry={'status':'error','last_checked':now,'changed':False,'new_courses':0,'last_changed':prior.get('last_changed'), 'content_hash':prior.get('content_hash')}
        try:
            response=requests.get(source['url'],headers=HEADERS,timeout=(8,25),allow_redirects=True)
            if response.status_code in (401,403,429):
                entry['status']='blocked'
                raise RuntimeError('HTTP '+str(response.status_code))
            response.raise_for_status()
            if len(response.content)>3_000_000: raise RuntimeError('page exceeds 3 MB')
            html=response.text
            soup=BeautifulSoup(html,'html.parser')
            for tag in soup(['script','style','noscript']):tag.decompose()
            txt=normalize(soup.get_text(' ',strip=True))[:150000]
            if len(txt)<90: raise RuntimeError('too little readable content')
            digest=hashlib.sha256(txt.encode()).hexdigest()[:16]
            changed=bool(prior.get('content_hash')) and digest != prior.get('content_hash')
            entry.update(status='ok',changed=changed,content_hash=digest,last_changed=now if changed else prior.get('last_changed'))
            successes+=1
            if source['collection']=='structured':
                found=parse_structured_page(source,html)
                for ev in found:
                    # Use title + start as matching key even when older data was
                    # manually seeded with a different stable hash or link.
                    match=next((key for key,old_ev in course_index.items() if old_ev.get('source_id')==sid and old_ev.get('start_date')==ev['start_date'] and re.sub(r'\W+','',old_ev.get('title','')).lower()==re.sub(r'\W+','',ev['title']).lower()),None)
                    if match:
                        prior_course=course_index[match]
                        # Preserve verified/manual price, link, language and
                        # location when scraper cannot infer those reliably.
                        for field in ('price_eur','language','city','country','mode','url'):
                            if ev.get(field) in (None,'待确认','地点待确认',source['url']) and prior_course.get(field) not in (None,'待确认'):
                                ev[field]=prior_course[field]
                        ev['id']=match
                        ev['origin']=prior_course.get('origin','官方网页人工核实')
                    else: newest+=1;entry['new_courses']+=1
                    course_index[ev['id']]=ev
            logging.info('%-17s %s | changed=%s new=%s',sid,entry['status'],changed,entry['new_courses'])
        except requests.RequestException as exc:
            logging.warning('%-17s %s',sid,str(exc)[:110])
        except Exception as exc:
            logging.warning('%-17s %s',sid,str(exc)[:110])
        statuses[sid]=entry
        if not dry_run: time.sleep(0.4)
    sorted_courses=sorted(course_index.values(),key=lambda c:(c['start_date'],c['provider'],c['title']))
    obj={'generated_at':now,'last_successful_scan':now if successes else previous.get('last_successful_scan'),'courses':sorted_courses,'source_status':statuses,'total_sources':len(sources)}
    return obj,{'successes':successes,'attempted':len(only) if only else len(sources),'new_courses':newest,'courses':len(sorted_courses)}


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--dry-run',action='store_true',help='run without writing files')
    ap.add_argument('--only',nargs='*',help='source IDs to scan (for debugging)')
    args=ap.parse_args()
    logging.basicConfig(level=logging.INFO,format='%(levelname)s %(message)s')
    sources=json.loads((DATA/'sources.json').read_text(encoding='utf-8'))
    old=json.loads((DATA/'courses.json').read_text(encoding='utf-8'))
    obj,summary=scan(sources,old,dry_run=args.dry_run,only=set(args.only or []) if args.only else None)
    logging.info('Scan summary: %s',summary)
    if not args.dry_run:
        (DATA/'courses.json').write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    # A total failure must not be presented as a successful refresh.
    return 0 if summary['successes'] else 2

if __name__=='__main__':sys.exit(main())