"""Historical browsing metadata and deterministic, renderer-free tree layout.

Connections describe role/time ordering, never research prerequisites or physics.
"""
from functools import lru_cache
from pathlib import Path
import json
from collections import Counter,defaultdict

HISTORY=Path(__file__).with_name('data')/'aircraft_history.json'
ROLES=(('fighter','战斗 / 截击机'),('attack','轰炸 / 攻击机'),('trainer','教练 / 试验机'),
       ('airliner','民航 / 公务机'),('support','运输 / 特种支援'))

@lru_cache(maxsize=1)
def document():
    doc=json.loads(HISTORY.read_text(encoding='utf8'))
    ids=[r['id'] for r in doc['aircraft']]
    if len(ids)!=len(set(ids)):raise ValueError('Duplicate aircraft history ID')
    return doc

@lru_cache(maxsize=1)
def history_index():return {r['id']:r for r in document()['aircraft']}

def history(row):
    id=row if isinstance(row,str) else row['id']
    return history_index().get(id,{'id':id,'country':'unclassified','role':'trainer','family':id,
        'decade':None,'date_basis':'unknown','status':'unknown','note':'新增资源，国家和年代待核实。','references':[]})

def countries(rows):
    counts=Counter(history(r)['country'] for r in rows)
    result=[{**c,'count':counts[c['id']]} for c in document()['countries'] if counts[c['id']]]
    if counts['unclassified']:result.append({'id':'unclassified','label':'待核实','count':counts['unclassified']})
    return result

def ordered(rows,country):
    return sorted((r for r in rows if history(r)['country']==country),key=lambda r:
        (history(r)['decade'] if history(r)['decade'] is not None else 9999,history(r)['role'],history(r)['family'],r['id']))

def decade_label(value):return f'{value}年代' if value is not None else '无现实年代'

def layout(rows,expanded=()):
    """Return bands and card positions in content coordinates; caller clips viewport.

    Every role gets its own fixed column. Two siblings can share a decade row.
    Family expansion reveals distinct playable resources without deduplication.
    """
    groups=defaultdict(list)
    for row in rows:
        h=history(row);groups[h['decade'],h['role'],h['family']].append(row)
    bands=[];nodes=[];offset=0
    for decade in sorted({k[0] for k in groups},key=lambda d:9999 if d is None else d):
        band={'decade':decade,'top':offset,'lanes':{}};maximum=1
        for lane,(role,_) in enumerate(ROLES):
            items=[]
            for key in sorted((k for k in groups if k[:2]==(decade,role)),key=lambda k:k[2]):
                members=sorted(groups[key],key=lambda r:r['id']);family=key[2]
                group_id=f'{decade}:{role}:{family}'
                if len(members)>1:
                    items.append({'kind':'family','group':group_id,'family':family,'members':members,'row':members[0]})
                    if group_id in expanded:items.extend({'kind':'aircraft','row':r,'child':True} for r in members)
                else:items.append({'kind':'aircraft','row':members[0]})
            maximum=max(maximum,(len(items)+1)//2)
            band['lanes'][role]=len(items)
            for i,item in enumerate(items):nodes.append({**item,'lane':lane,'x':145+lane*340+(i%2)*158,'y':offset+35+(i//2)*96,'decade':decade})
        band['height']=maximum*96+44;bands.append(band);offset+=band['height']
    return {'bands':bands,'nodes':nodes,'height':offset}
