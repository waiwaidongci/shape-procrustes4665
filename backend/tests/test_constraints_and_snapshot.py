import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from src.config.database import Session
from src.models import (
    Template,TemplateVersion,TemplateMigration,ShapeSpecimen,ShapeCollection,
)
from src.services.deformation import analyze_alignment
from tests.conftest import LABELS,POINTS,make_template,make_collection,make_specimen,rotate_labels,rotated_points,rotation_mapping

def test_open_migration_partial_index_blocks_two_open_rows():
    with Session() as db:
        t=make_template(db)
        v2=TemplateVersion(template_id=t.id,version=2,labels=rotate_labels(1),points=rotated_points(POINTS,1),convention='',is_active=False)
        db.add(v2);db.flush()
        v1=db.scalar(select(TemplateVersion).where(TemplateVersion.template_id==t.id,TemplateVersion.version==1))
        db.add(TemplateMigration(name='a',template_id=t.id,from_version_id=v1.id,to_version_id=v2.id,status='draft',label_mapping=rotation_mapping(1),point_mapping=[0]*8))
        db.commit()
        db.add(TemplateMigration(name='b',template_id=t.id,from_version_id=v1.id,to_version_id=v2.id,status='conflict',label_mapping=rotation_mapping(1),point_mapping=[0]*8))
        with pytest.raises(IntegrityError):db.commit()
        db.rollback()
        # A completed migration frees the slot for a new open one.
        db.scalar(select(TemplateMigration).where(TemplateMigration.name=='a')).status='completed';db.commit()
        db.add(TemplateMigration(name='c',template_id=t.id,from_version_id=v1.id,to_version_id=v2.id,status='draft',label_mapping=rotation_mapping(1),point_mapping=[0]*8))
        db.commit()  # must not raise

def test_single_active_version_index_blocks_two_actives():
    with Session() as db:
        t=make_template(db)
        db.add(TemplateVersion(template_id=t.id,version=2,labels=LABELS.copy(),points=[p.copy() for p in POINTS],convention='',is_active=True))
        with pytest.raises(IntegrityError):db.commit()
        db.rollback()
        # inactive historical versions coexist fine
        db.add(TemplateVersion(template_id=t.id,version=2,labels=LABELS.copy(),points=[p.copy() for p in POINTS],convention='',is_active=False))
        db.commit()
        actives=db.scalars(select(TemplateVersion).where(TemplateVersion.template_id==t.id,TemplateVersion.is_active.is_(True))).all()
        assert len(actives)==1 and actives[0].version==1

def test_gpa_analysis_runs_on_versioned_snapshot():
    with Session() as db:
        t=make_template(db);c=make_collection(db,t)
        make_specimen(db,c,'S1',points=[[float(i),float(i%3)] for i in range(8)])
        make_specimen(db,c,'S2',points=[[float(i)+0.5,float((i+1)%3)] for i in range(8)])
        v=db.scalar(select(TemplateVersion).where(TemplateVersion.template_id==t.id,TemplateVersion.is_active.is_(True)))
        snapshot={'collection':{'id':c.id,'code':c.code,'name':c.name,'protocol':'','source_file':'','template_id':t.id},
                  'template':{'id':t.id,'code':t.code,'name':t.name,'labels':v.labels,'points':v.points,'convention':v.convention,'version':1,'template_version_id':v.id},
                  'specimens':[{k:getattr(s,k) for k in ('id','code','name','points','source_note','template_version','revision')} for s in db.scalars(select(ShapeSpecimen)).all()]}
        result=analyze_alignment(snapshot,1,1e-9)
        assert result['converged'] is True
        assert result['labels']==LABELS
        assert len(result['specimens'])==2
        assert 'version' in result['snapshot']['template']
