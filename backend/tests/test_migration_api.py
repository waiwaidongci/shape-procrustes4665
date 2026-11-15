import pytest
from sqlalchemy import select
from src.config.database import Session
from src.models import Template,TemplateMigration,ShapeSpecimen
from src.schemas.migration import MigrationCreate
from src.services import migration_service as ms
from tests.conftest import make_template,make_collection,make_specimen,rotate_labels,rotated_points,rotation_mapping,LABELS,POINTS

class U:
    def __init__(self,email):self.email=email
ANALYST=U('analyst@tinglan.local')

def _specimen_payload(s,token):
    return {'collection_id':s['collection_id'],'code':s['code'],'name':s['name'],'points':s['points'],'source_note':s['source_note'],'template_version':token}

def test_stale_page_save_rejected_with_409_and_reload_then_ok(client):
    h_analyst=None
    with Session() as db:
        t=make_template(db);c=make_collection(db,t);s=make_specimen(db,c,'S1')
        tid,cid,sid=t.id,c.id,s.id
        n=1
        m=ms.create_migration(db,MigrationCreate(name='http',template_id=tid,labels=rotate_labels(n),points=rotated_points(POINTS,n),label_mapping=rotation_mapping(n)),ANALYST.email)
        ms.activate_migration(db,m.id,ANALYST.email)
        new_points=db.get(ShapeSpecimen,sid).points
    h=client.post('/auth/login',json={'email':'analyst@tinglan.local','password':'Tinglan2026!'}).json()
    headers={'Authorization':'Bearer '+h['token']}
    # Old page still holds token v1 -> explicit rejection.
    stale=_specimen_payload({'collection_id':cid,'code':'S1','name':'裁片S1','points':POINTS,'source_note':'src'},1)
    r=client.put(f'/specimens/{sid}',json=stale,headers=headers)
    assert r.status_code==409
    assert '过期' in r.json()['detail'] and '重载' in r.json()['detail']
    # Reload gives v2 token; saving against current order succeeds.
    fresh=client.get(f'/specimens?collection_id={cid}',headers=headers).json()[0]
    assert fresh['template_version']==2
    ok={**_specimen_payload(fresh,2),'points':[[p[0]+1,p[1]] for p in fresh['points']]}
    r2=client.put(f'/specimens/{sid}',json=ok,headers=headers)
    assert r2.status_code==200 and r2.json()['template_version']==2

def test_create_specimen_ignores_client_version_and_uses_active(client):
    h=client.post('/auth/login',json={'email':'analyst@tinglan.local','password':'Tinglan2026!'}).json()
    headers={'Authorization':'Bearer '+h['token']}
    with Session() as db:
        t=make_template(db);c=make_collection(db,t);cid=t.id and c.id
    body={'collection_id':cid,'code':'NEW1','name':'裁片NEW1','points':POINTS,'source_note':'x','template_version':99}
    r=client.post('/specimens',json=body,headers=headers)
    assert r.status_code==201 and r.json()['template_version']==1

def test_viewer_cannot_write_migration_or_specimen(client):
    with Session() as db:
        t=make_template(db);c=make_collection(db,t);make_specimen(db,c,'S1');tid=t.id
    hv=client.post('/auth/login',json={'email':'viewer@tinglan.local','password':'Tinglan2026!'}).json()
    headers={'Authorization':'Bearer '+hv['token']}
    r=client.post('/migrations',json={'name':'x','template_id':tid,'labels':rotate_labels(1),'points':rotated_points(POINTS,1),'label_mapping':rotation_mapping(1)},headers=headers)
    assert r.status_code==403
    r=client.get('/migrations',headers=headers)
    assert r.status_code==200  # read is allowed

def test_template_in_place_label_change_rejected_with_migration_guidance(client):
    h=client.post('/auth/login',json={'email':'analyst@tinglan.local','password':'Tinglan2026!'}).json()
    headers={'Authorization':'Bearer '+h['token']}
    with Session() as db:
        t=make_template(db);tid=t.id
    body={'code':'TL-8-1','name':'模板TL-8-1','labels':rotate_labels(1),'points':rotated_points(POINTS,1),'convention':'v1约定'}
    r=client.put(f'/templates/{tid}',json=body,headers=headers)
    assert r.status_code==422 and '改版' in r.json()['detail']
    # name/convention only is accepted
    ok=client.put(f'/templates/{tid}',json={'code':'TL-8-1','name':'改名模板','labels':LABELS.copy(),'points':[p.copy() for p in POINTS],'convention':'新约定'},headers=headers)
    assert ok.status_code==200

def test_full_migration_http_flow_and_progress_visibility(client):
    h=client.post('/auth/login',json={'email':'admin@tinglan.local','password':'Tinglan2026!'}).json()
    headers={'Authorization':'Bearer '+h['token']}
    with Session() as db:
        t=make_template(db);c=make_collection(db,t);make_specimen(db,c,'S1');make_specimen(db,c,'S2');tid=t.id;cid=c.id
    n=2
    r=client.post('/migrations',json={'name':'http-flow','template_id':tid,'labels':rotate_labels(n),'points':rotated_points(POINTS,n),'label_mapping':rotation_mapping(n)},headers=headers)
    assert r.status_code==201
    mid=r.json()['id']
    assert len(r.json()['items'])==2 and r.json()['summary']['total']==2
    detail=client.get(f'/migrations/{mid}',headers=headers).json()
    assert detail['items'][0]['after_points']==rotated_points(POINTS,n)
    act=client.post(f'/migrations/{mid}/activate',headers=headers)
    assert act.status_code==200 and act.json()['status']=='completed'
    versions=client.get(f'/templates/{tid}/versions',headers=headers).json()
    assert [v['version'] for v in versions]==[1,2] and versions[1]['is_active'] is True
    listing=client.get('/migrations',headers=headers).json()
    assert listing[0]['summary']['applied']==2

def test_rebase_http_endpoint_clears_conflict(client):
    h=client.post('/auth/login',json={'email':'analyst@tinglan.local','password':'Tinglan2026!'}).json()
    headers={'Authorization':'Bearer '+h['token']}
    with Session() as db:
        t=make_template(db);c=make_collection(db,t);s=make_specimen(db,c,'S1');tid=t.id;sid=s.id
        n=1
        m=ms.create_migration(db,MigrationCreate(name='rb',template_id=tid,labels=rotate_labels(n),points=rotated_points(POINTS,n),label_mapping=rotation_mapping(n)),ANALYST.email);mid=m.id
        from src.schemas.specimen import SpecimenInput
        from src.services import specimen_service
        corrected=[[p[0]+5,p[1]] for p in POINTS]
        specimen_service.update_specimen(db,sid,SpecimenInput(collection_id=c.id,code='S1',name='裁片S1',points=corrected,source_note='src',template_version=1))
        with pytest.raises(Exception):ms.activate_migration(db,mid,ANALYST.email)
        assert ms.get_migration(db,mid).status=='conflict'
        item_id=ms.list_items(db,mid)[0].id
    r=client.post(f'/migrations/{mid}/items/{item_id}/rebase',headers=headers)
    assert r.status_code==200 and r.json()['status']=='draft'
    act=client.post(f'/migrations/{mid}/activate',headers=headers)
    assert act.json()['status']=='completed'
