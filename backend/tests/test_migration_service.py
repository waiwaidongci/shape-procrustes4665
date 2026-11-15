import pytest
from sqlalchemy import select
from src.config.database import Session
from src.models import Template,TemplateVersion,ShapeSpecimen,ShapeCollection,TemplateMigration,TemplateMigrationItem
from src.schemas.migration import MigrationCreate
from src.services import migration_service as ms
from src.services.template_service import bootstrap_versions,active_version
from tests.conftest import LABELS,POINTS,make_template,make_collection,make_specimen,rotate_labels,rotated_points,identity_mapping,rotation_mapping

class U:
    def __init__(self,email):self.email=email
ADMIN=U('admin@tinglan.local');ANALYST=U('analyst@tinglan.local')

def new_labels(n):return rotate_labels(n)
def new_points(n):return rotated_points(POINTS,n)

# 1. Legacy bootstrap -------------------------------------------------------
def test_bootstrap_creates_v1_and_stamps_specimens():
    with Session() as db:
        t=Template(code='B1',name='b',labels=LABELS.copy(),points=[p.copy() for p in POINTS],convention='c');db.add(t);db.flush()
        c=ShapeCollection(code='BC1',name='c',template_id=t.id,protocol='',source_file='');db.add(c);db.flush()
        db.add(ShapeSpecimen(collection_id=c.id,code='S1',name='s',points=[p.copy() for p in POINTS],source_note=''))
        db.commit();tid=t.id;cid=c.id
    with Session() as db:
        bootstrap_versions(db)
        vs=db.scalars(select(TemplateVersion).where(TemplateVersion.template_id==tid)).all()
        assert len(vs)==1 and vs[0].version==1 and vs[0].is_active
        assert db.get(ShapeSpecimen,db.scalar(select(ShapeSpecimen.id))).template_version==1
    # idempotent
    with Session() as db:
        bootstrap_versions(db)
        assert len(db.scalars(select(TemplateVersion).where(TemplateVersion.template_id==tid)).all())==1

# 2. Mapping validation ------------------------------------------------------
def test_mapping_missing_and_duplicate_rejected():
    with Session() as db:
        t=make_template(db);make_collection(db,t)
        bad_missing={l:l for l in LABELS[:7]};bad_missing['LX']='L1'
        with pytest.raises(Exception) as e:
            ms.create_migration(db,MigrationCreate(name='m1',template_id=t.id,labels=new_labels(2),points=new_points(2),label_mapping=bad_missing),ANALYST.email)
        assert '缺漏' in str(e.value)
        db.rollback()
        dup={LABELS[i]:LABELS[0] for i in range(8)}
        with pytest.raises(Exception):
            ms.create_migration(db,MigrationCreate(name='m2',template_id=t.id,labels=new_labels(2),points=new_points(2),label_mapping=dup),ANALYST.email)
        db.rollback()
        assert db.scalar(select(TemplateMigration.id)) is None

def test_mapping_not_covering_new_labels_rejected():
    with Session() as db:
        t=make_template(db)
        # Values cover only 7 distinct new labels: one duplicated, one missing.
        new=rotate_labels(1)
        mapping={LABELS[i]:(new[i] if i<7 else new[0]) for i in range(8)}
        with pytest.raises(Exception) as e:
            ms.create_migration(db,MigrationCreate(name='m3',template_id=t.id,labels=new,points=new_points(1),label_mapping=mapping),ANALYST.email)
        assert '覆盖' in str(e.value) or '重复' in str(e.value)

# 3. Full migration across two collections ----------------------------------
def test_full_migration_remaps_all_specimens_and_activates():
    with Session() as db:
        t=make_template(db);c1=make_collection(db,t,'C1');c2=make_collection(db,t,'C2')
        s1=make_specimen(db,c1,'S1');s2=make_specimen(db,c2,'S2');s3=make_specimen(db,c2,'S3')
        n=2
        m=ms.create_migration(db,MigrationCreate(name='full',template_id=t.id,labels=new_labels(n),points=new_points(n),label_mapping=rotation_mapping(n)),ANALYST.email)
        assert m.status=='draft'
        items=ms.list_items(db,m.id)
        assert {it.specimen_id for it in items}=={s1.id,s2.id,s3.id}
        # point_mapping derived from the same label bijection and destination
        # label order the service uses.
        from tests.conftest import expected_point_mapping
        dest=new_labels(n)
        assert m.point_mapping==expected_point_mapping(rotation_mapping(n),dest)
        assert items[0].after_points==rotated_points(POINTS,n,dest)
        ms.activate_migration(db,m.id,ANALYST.email)
        m=ms.get_migration(db,m.id)
        assert m.status=='completed'
        assert active_version(db,t.id).version==2
        for s in (db.get(ShapeSpecimen,s1.id),db.get(ShapeSpecimen,s2.id),db.get(ShapeSpecimen,s3.id)):
            assert s.template_version==2
            assert s.points==rotated_points(POINTS,n)
        # only one active version
        actives=db.scalars(select(TemplateVersion).where(TemplateVersion.template_id==t.id,TemplateVersion.is_active.is_(True))).all()
        assert len(actives)==1 and actives[0].version==2
        assert m.summary['applied']==3 and m.summary['failed']==0 and m.summary['stale']==0

# 4. Correction during window -> conflict -> rebase -> activate --------------
def test_correction_during_window_conflict_then_rebase():
    with Session() as db:
        t=make_template(db);c=make_collection(db,t);s=make_specimen(db,c,'S1')
        n=1;m=ms.create_migration(db,MigrationCreate(name='corr',template_id=t.id,labels=new_labels(n),points=new_points(n),label_mapping=rotation_mapping(n)),ANALYST.email)
        corrected=[ [p[0]+10.0,p[1]+20.0] for p in POINTS ]
        # A real correction goes through the service, which bumps the revision.
        from src.schemas.specimen import SpecimenInput
        from src.services import specimen_service
        specimen_service.update_specimen(db,s.id,SpecimenInput(collection_id=c.id,code='S1',name='裁片S1',points=corrected,source_note='src',template_version=1))
        item=ms.list_items(db,m.id)[0]
        assert item.before_points!=corrected
        assert item.source_specimen_revision==1
        assert db.get(ShapeSpecimen,s.id).revision==2
        with pytest.raises(Exception) as e:
            ms.activate_migration(db,m.id,ANALYST.email)
        assert '追齐' in str(e.value)
        m=ms.get_migration(db,m.id);assert m.status=='conflict'
        it=ms.list_items(db,m.id)[0];assert it.status=='stale'
        # correction must not have been overwritten
        assert db.get(ShapeSpecimen,s.id).points==corrected
        assert db.get(ShapeSpecimen,s.id).template_version==1
        # rebase carries the correction forward
        ms.rebase_item(db,m.id,it.id,ANALYST.email)
        it=ms.list_items(db,m.id)[0];assert it.status=='pending'
        assert it.source_specimen_revision==2
        assert it.before_points==corrected and it.after_points==rotated_points(corrected,n,new_labels(n))
        ms.activate_migration(db,m.id,ANALYST.email)
        assert ms.get_migration(db,m.id).status=='completed'
        s=db.get(ShapeSpecimen,s.id)
        assert s.template_version==2 and s.points==rotated_points(corrected,n,new_labels(n))

# 5. Interrupted recovery is re-entrant --------------------------------------
def test_interrupted_activation_recovers_without_overwrite():
    with Session() as db:
        t=make_template(db);c=make_collection(db,t)
        specs=[make_specimen(db,c,f'S{i}') for i in range(4)]
        n=3;m=ms.create_migration(db,MigrationCreate(name='interrupt',template_id=t.id,labels=new_labels(n),points=new_points(n),label_mapping=rotation_mapping(n)),ANALYST.email)
        # Simulate a partial activation: apply first two items directly at v2.
        items=ms.list_items(db,m.id)
        for it in items[:2]:
            sp=db.get(ShapeSpecimen,it.specimen_id)
            sp.points=rotated_points(sp.points,n);sp.template_version=2
            it.status='applied'
        db.commit()
        m.status='in_progress';db.commit()
        # Recovery re-activation finishes the rest.
        ms.activate_migration(db,m.id,ANALYST.email)
        m=ms.get_migration(db,m.id);assert m.status=='completed'
        for sp_id in [s.id for s in specs]:
            sp=db.get(ShapeSpecimen,sp_id)
            assert sp.template_version==2 and sp.points==rotated_points(POINTS,n)
        assert m.summary['applied']==4

# 6. Concurrency: one open migration, one active version ---------------------
def test_concurrent_open_migration_rejected():
    with Session() as db:
        t=make_template(db);make_collection(db,t)
        ms.create_migration(db,MigrationCreate(name='one',template_id=t.id,labels=new_labels(1),points=new_points(1),label_mapping=rotation_mapping(1)),ANALYST.email)
        with pytest.raises(Exception) as e:
            ms.create_migration(db,MigrationCreate(name='two',template_id=t.id,labels=new_labels(2),points=new_points(2),label_mapping=rotation_mapping(2)),ANALYST.email)
        assert '一个版本生效' in str(e.value)
        db.rollback()
        # completing the first allows the next revision
        first=db.scalar(select(TemplateMigration))
        ms.activate_migration(db,first.id,ANALYST.email)
        m2=ms.create_migration(db,MigrationCreate(name='two',template_id=t.id,labels=new_labels(2),points=new_points(2),label_mapping=rotation_mapping(1)),ANALYST.email)
        assert m2.from_version_id!=m2.to_version_id
        assert active_version(db,t.id).version==2

# 8. Run snapshot freezes whole old or new version ----------------------------
def test_run_freezes_complete_versions_and_history_untouched():
    from src.schemas.run import RunInput
    from src.services import run_service
    with Session() as db:
        t=make_template(db);c=make_collection(db,t);make_specimen(db,c,'S1');make_specimen(db,c,'S2')
        r1=run_service.create_run(db,RunInput(name='run-old',collection_id=c.id,retained=1,tolerance=1e-9))
        assert r1.snapshot['template']['version']==1
        assert all(sp['template_version']==1 for sp in r1.snapshot['specimens'])
        n=2
        m=ms.create_migration(db,MigrationCreate(name='v2',template_id=t.id,labels=new_labels(n),points=new_points(n),label_mapping=rotation_mapping(n)),ANALYST.email)
        # queued run during migration still sees the complete OLD version
        r_mid=run_service.create_run(db,RunInput(name='run-mid',collection_id=c.id,retained=1,tolerance=1e-9))
        assert r_mid.snapshot['template']['version']==1
        ms.activate_migration(db,m.id,ANALYST.email)
        r2=run_service.create_run(db,RunInput(name='run-new',collection_id=c.id,retained=1,tolerance=1e-9))
        assert r2.snapshot['template']['version']==2
        assert r2.snapshot['template']['labels']==new_labels(n)
        assert all(sp['template_version']==2 for sp in r2.snapshot['specimens'])
        # historical frozen snapshot untouched
        old=db.get(type(r1),r1.id)
        assert old.snapshot['template']['version']==1
        assert old.snapshot['template']['labels']==LABELS

# 9. Cancel semantics ---------------------------------------------------------
def test_cancel_leaves_data_untouched_and_terminal_locked():
    with Session() as db:
        t=make_template(db);c=make_collection(db,t);s=make_specimen(db,c,'S1')
        m=ms.create_migration(db,MigrationCreate(name='cancelme',template_id=t.id,labels=new_labels(1),points=new_points(1),label_mapping=rotation_mapping(1)),ANALYST.email)
        ms.cancel_migration(db,m.id,ANALYST.email)
        assert ms.get_migration(db,m.id).status=='cancelled'
        assert active_version(db,t.id).version==1
        assert db.get(ShapeSpecimen,s.id).points==POINTS
        with pytest.raises(Exception):ms.activate_migration(db,m.id,ANALYST.email)
        with pytest.raises(Exception):ms.cancel_migration(db,m.id,ANALYST.email)

# 10. New specimen added after preview is enqueued on activate ----------------
def test_new_specimen_after_preview_is_included():
    with Session() as db:
        t=make_template(db);c=make_collection(db,t);s1=make_specimen(db,c,'S1')
        n=1;m=ms.create_migration(db,MigrationCreate(name='late',template_id=t.id,labels=new_labels(n),points=new_points(n),label_mapping=rotation_mapping(n)),ANALYST.email)
        s2=make_specimen(db,c,'S2')  # added after preview, already v1 active
        ms.activate_migration(db,m.id,ANALYST.email)
        assert ms.get_migration(db,m.id).status=='completed'
        assert db.get(ShapeSpecimen,s2.id).template_version==2
        assert db.get(ShapeSpecimen,s2.id).points==rotated_points(POINTS,n)

# All conflicts rebased -> migration reopens for activation ------------------
def test_all_conflicts_rebased_reopens_draft_then_completes():
    from src.schemas.specimen import SpecimenInput
    from src.services import specimen_service
    with Session() as db:
        t=make_template(db);c=make_collection(db,t)
        specs=[make_specimen(db,c,f'S{i}') for i in range(3)]
        n=1
        m=ms.create_migration(db,MigrationCreate(name='multi-conflict',template_id=t.id,labels=new_labels(n),points=new_points(n),label_mapping=rotation_mapping(n)),ANALYST.email)
        for sp in specs:
            specimen_service.update_specimen(db,sp.id,SpecimenInput(collection_id=c.id,code=sp.code,name=sp.name,points=[[p[0]+1,p[1]] for p in POINTS],source_note='src',template_version=1))
        with pytest.raises(Exception):ms.activate_migration(db,m.id,ANALYST.email)
        assert ms.get_migration(db,m.id).status=='conflict'
        for it in ms.list_items(db,m.id):
            ms.rebase_item(db,m.id,it.id,ANALYST.email)
        assert ms.get_migration(db,m.id).status=='draft'
        ms.activate_migration(db,m.id,ANALYST.email)
        m=ms.get_migration(db,m.id);assert m.status=='completed'
        assert m.summary['applied']==3 and m.summary['stale']==0

# Identity mapping (labels unchanged, only reference points adjusted) --------
def test_identity_mapping_keeps_coordinates_in_place():
    with Session() as db:
        t=make_template(db);c=make_collection(db,t);s=make_specimen(db,c,'S1')
        shifted=[[p[0]+1.0,p[1]] for p in POINTS]
        m=ms.create_migration(db,MigrationCreate(name='ident',template_id=t.id,labels=LABELS.copy(),points=shifted,label_mapping=identity_mapping()),ANALYST.email)
        assert m.point_mapping==list(range(8))
        ms.activate_migration(db,m.id,ANALYST.email)
        assert db.get(ShapeSpecimen,s.id).points==POINTS
        assert active_version(db,t.id).points==shifted
