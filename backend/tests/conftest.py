import os
import pathlib
import pytest

_DB_PATH=pathlib.Path('/tmp/pytest_shapes.db')
if _DB_PATH.exists():_DB_PATH.unlink()
os.environ['DATABASE_URL']=f'sqlite:///{_DB_PATH}'
os.environ['SEED_DEMO']='false'
os.environ['REDIS_URL']='redis://fake/0'

class _FakeRedis:
    def __init__(self,*a,**k):self.items=[];self.counters={}
    def lpush(self,key,value):self.items.append((key,value))
    def brpop(self,keys,timeout=0):return None
    def incr(self,key):
        self.counters[key]=self.counters.get(key,0)+1;return self.counters[key]
    def expire(self,key,seconds):return True
    def ping(self):return True

import redis as _redis
_redis.Redis.from_url=staticmethod(lambda *a,**k:_FakeRedis())

from fastapi.testclient import TestClient
from sqlalchemy import select
from src.main import app
from src.config.database import Base,engine,Session
from src.services.template_service import bootstrap_versions
from src.models import User,Template,ShapeCollection,ShapeSpecimen,TemplateVersion
from src.utils.security import hash_password

LABELS=[f'L{i+1}' for i in range(8)]
POINTS=[[float(i),float((i*2)%8)] for i in range(8)]

@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.drop_all(engine);Base.metadata.create_all(engine)
    with Session() as session:
        for role,email in [('admin','admin@tinglan.local'),('analyst','analyst@tinglan.local'),('viewer','viewer@tinglan.local')]:
            session.add(User(email=email,name=role,role=role,password_hash=hash_password('Tinglan2026!')))
        session.commit()
    yield

@pytest.fixture()
def db():
    yield Session

def bootstrap():
    with Session() as db:bootstrap_versions(db)

@pytest.fixture()
def client():
    with TestClient(app) as c:yield c

def auth(client,role='analyst'):
    r=client.post('/auth/login',json={'email':f'{role}@tinglan.local','password':'Tinglan2026!'})
    assert r.status_code==200,r.text
    return {'Authorization':'Bearer '+r.json()['token']}

def make_template(db,code='TL-8-1',labels=None,points=None):
    t=Template(code=code,name='模板'+code,labels=labels or LABELS.copy(),points=points or [p.copy() for p in POINTS],convention='v1约定')
    db.add(t);db.flush()
    db.add(TemplateVersion(template_id=t.id,version=1,labels=t.labels,points=t.points,convention=t.convention,is_active=True,created_by='test'))
    db.commit();return t

def make_collection(db,template,code='C1',name='集合'):
    c=ShapeCollection(code=code,name=name,template_id=template.id,protocol='p',source_file=code+'.csv')
    db.add(c);db.commit();return c

def make_specimen(db,collection,code,points=None,version=1):
    s=ShapeSpecimen(collection_id=collection.id,code=code,name='裁片'+code,points=points or [p.copy() for p in POINTS],source_note='src',template_version=version)
    db.add(s);db.commit();return s

def rotate_labels(n):
    """New label order rotated by n; identity geometric points keep 8x2 shape."""
    return LABELS[n:]+LABELS[:n]

def rotated_points(points,n,new_labels=None):
    # Expected remap under rotation_mapping(n). Derived from the label mapping
    # against the DESTINATION label order, exactly like the service validator.
    dest=new_labels if new_labels is not None else rotate_labels(n)
    to_index={label:i for i,label in enumerate(dest)}
    pm=[0]*8
    for old_i,old_label in enumerate(LABELS):
        pm[to_index[rotation_mapping(n)[old_label]]]=old_i
    return [list(points[j]) for j in pm]

def expected_point_mapping(label_mapping,dest_labels):
    to_index={label:i for i,label in enumerate(dest_labels)}
    pm=[0]*8
    for old_i,old_label in enumerate(LABELS):
        pm[to_index[label_mapping[old_label]]]=old_i
    return pm

def identity_mapping():return {l:l for l in LABELS}

def rotation_mapping(n):
    # old label at old index i moves to new index (i-n)%8
    return {LABELS[i]:LABELS[(i-n)%8] for i in range(8)}
