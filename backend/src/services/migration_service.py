"""Versioned template revision with per-point remap across shared collections.

Concurrency model:
* a partial unique index allows at most one open migration per template;
* activation runs in a single transaction with row locks (no-op on SQLite);
* per-specimen conditional updates never overwrite a revision newer than the
  migration's recorded source version, so interrupted recovery is safe and
  re-entrant; only one template version can be active (partial unique index).
"""
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
from redis import Redis
from src.config.settings import REDIS_URL
from src.models import (
    Template,TemplateVersion,TemplateMigration,TemplateMigrationItem,
    ShapeCollection,ShapeSpecimen,
)
from src.services.template_service import active_version,get_template
from src.constants.enums import MigrationStatus as MS,MigrationItemStatus as IS

redis=Redis.from_url(REDIS_URL)
OPEN_STATUSES=(MS.DRAFT,MS.IN_PROGRESS,MS.CONFLICT)
TERMINAL_STATUSES=(MS.COMPLETED,MS.CANCELLED)

# ---------- mapping helpers ----------

def validate_mapping(from_labels:list[str],to_labels:list[str],label_mapping:dict)->list[int]:
    """Return point_mapping where after[i] = before[point_mapping[i]]."""
    if not isinstance(label_mapping,dict) or len(label_mapping)!=8:
        raise HTTPException(422,'映射必须包含8个旧标签到新标签的逐点对应')
    if set(label_mapping.keys())!=set(from_labels):
        raise HTTPException(422,'映射缺漏旧标签或包含不属于旧版本的标签，未做切换')
    values=list(label_mapping.values())
    if len(set(values))!=8:
        raise HTTPException(422,'映射存在重复的新标签，未做切换')
    if set(values)!=set(to_labels):
        raise HTTPException(422,'映射未覆盖全部8个新版标签，未做切换')
    to_index={label:i for i,label in enumerate(to_labels)}
    point_mapping=[0]*8
    for old_i,old_label in enumerate(from_labels):
        point_mapping[to_index[label_mapping[old_label]]]=old_i
    return point_mapping

def remap_points(points:list,point_mapping:list[int])->list:
    return [list(points[j]) for j in point_mapping]

def _locked(db,stmt):
    """Row lock on Postgres; SQLite serializes writes and ignores FOR UPDATE."""
    if db.bind.dialect.name=='sqlite':
        return db.scalars(stmt).all()
    return db.scalars(stmt.with_for_update()).all()

# ---------- queries ----------

def list_migrations(db):
    return db.scalars(select(TemplateMigration).order_by(TemplateMigration.id.desc())).all()

def get_migration(db,migration_id):
    m=db.get(TemplateMigration,migration_id)
    if not m:raise HTTPException(404,'模板改版任务不存在')
    return m

def list_items(db,migration_id):
    return db.scalars(select(TemplateMigrationItem).where(TemplateMigrationItem.migration_id==migration_id).order_by(TemplateMigrationItem.collection_id,TemplateMigrationItem.specimen_id)).all()

def _open_migration(db,template_id):
    return db.scalar(select(TemplateMigration).where(TemplateMigration.template_id==template_id,TemplateMigration.status.in_(OPEN_STATUSES)))

def _summary(db,m:TemplateMigration)->dict:
    items=list_items(db,m.id)
    counts={s.value:0 for s in IS}
    per_collection={}
    conflicts=[]
    for it in items:
        counts[it.status]=counts.get(it.status,0)+1
        c=per_collection.setdefault(it.collection_id,{'collection_id':it.collection_id,'total':0,'applied':0,'pending':0,'failed':0,'stale':0})
        c['total']+=1;c[it.status]=c.get(it.status,0)+1
        if it.status in (IS.FAILED,IS.STALE):
            s=db.get(ShapeSpecimen,it.specimen_id)
            conflicts.append({'item_id':it.id,'specimen_id':it.specimen_id,'code':s.code if s else '','status':it.status,'message':it.message,'recorded_version':it.source_specimen_version,'recorded_revision':it.source_specimen_revision,'current_version':s.template_version if s else None,'current_revision':s.revision if s else None})
    return {'total':len(items),'applied':counts.get(IS.APPLIED,0),'pending':counts.get(IS.PENDING,0),'failed':counts.get(IS.FAILED,0),'stale':counts.get(IS.STALE,0),'collections':list(per_collection.values()),'conflicts':conflicts}

# ---------- lifecycle ----------

def create_migration(db,data,actor:str):
    t=get_template(db,data.template_id)
    if not data.labels_unique_ok:raise HTTPException(422,'新版8个同源角点标签必须唯一')
    if _open_migration(db,t.id):raise HTTPException(409,'该模板已有进行中的改版任务，并发发布只允许一个版本生效')
    from_v=active_version(db,t.id)
    point_mapping=validate_mapping(from_v.labels,data.labels,data.label_mapping)
    next_no=db.scalar(select(TemplateVersion.version).where(TemplateVersion.template_id==t.id).order_by(TemplateVersion.version.desc()))+1
    to_v=TemplateVersion(template_id=t.id,version=next_no,labels=data.labels,points=data.points,convention=data.convention,is_active=False,created_by=actor)
    db.add(to_v);db.flush()
    m=TemplateMigration(name=data.name,template_id=t.id,from_version_id=from_v.id,to_version_id=to_v.id,status=MS.DRAFT,label_mapping=data.label_mapping,point_mapping=point_mapping,created_by=actor)
    db.add(m);db.flush()
    collections=db.scalars(select(ShapeCollection).where(ShapeCollection.template_id==t.id)).all()
    for c in collections:
        for s in db.scalars(select(ShapeSpecimen).where(ShapeSpecimen.collection_id==c.id).order_by(ShapeSpecimen.code)).all():
            before=[list(p) for p in s.points]
            db.add(TemplateMigrationItem(migration_id=m.id,specimen_id=s.id,collection_id=c.id,status=IS.PENDING,before_points=before,after_points=remap_points(before,point_mapping),source_specimen_version=s.template_version,source_specimen_revision=s.revision))
    m.summary=_summary(db,m)
    try:
        db.commit()
    except IntegrityError:
        db.rollback();raise HTTPException(409,'该模板已有进行中的改版任务，并发发布只允许一个版本生效')
    return get_migration(db,m.id)

def _mark_conflict(db,m:TemplateMigration,reason:str):
    """Persist conflict state after a rolled-back activation attempt.

    Only genuinely stale/missing items become conflicts; untouched pending items
    stay pending so a later activation carries them without a manual catch-up.
    """
    for it in list_items(db,m.id):
        if it.status==IS.APPLIED:continue
        s=db.get(ShapeSpecimen,it.specimen_id)
        if s is None:
            it.status=IS.FAILED;it.message='裁片已不存在'
        elif s.template_version!=it.source_specimen_version or s.revision!=it.source_specimen_revision:
            it.status=IS.STALE;it.message=f'迁移期间裁片被更正（记录v{it.source_specimen_version}r{it.source_specimen_revision}→当前v{s.template_version}r{s.revision}），请追齐后再切换'
        else:
            # Untouched rows stay pending with a clean message; only genuinely
            # stale/missing rows become conflicts.
            it.status=IS.PENDING;it.message=''
    m.status=MS.CONFLICT;m.summary=_summary(db,m);db.commit()

def activate_migration(db,migration_id,actor:str=''):
    m=get_migration(db,migration_id)
    if m.status==MS.COMPLETED:return m  # idempotent recovery
    if m.status==MS.CANCELLED:raise HTTPException(409,'改版任务已取消，不能再切换')
    from_v=db.get(TemplateVersion,m.from_version_id);to_v=db.get(TemplateVersion,m.to_version_id)
    # Re-validate the bijection at switch time as well; a bad mapping never switches.
    validate_mapping(from_v.labels,to_v.labels,m.label_mapping)
    m.status=MS.IN_PROGRESS;db.commit()
    try:redis.lpush('shapes:migrations',str(m.id))
    except Exception:pass
    try:
        with db.begin():
            # Lock the migration, its template and every affected specimen.
            _locked(db,select(TemplateMigration).where(TemplateMigration.id==m.id))
            _locked(db,select(Template).where(Template.id==m.template_id))
            other=_open_migration(db,m.template_id)
            if other and other.id!=m.id:raise HTTPException(409,'存在另一个进行中的改版任务，本次切换中止')
            if to_v.is_active:raise HTTPException(409,'目标版本已生效，无需重复切换')
            # Specimens added after migration creation are enqueued automatically.
            known={it.specimen_id for it in list_items(db,m.id)}
            collections=db.scalars(select(ShapeCollection).where(ShapeCollection.template_id==m.template_id)).all()
            for c in collections:
                for s in db.scalars(select(ShapeSpecimen).where(ShapeSpecimen.collection_id==c.id)).all():
                    if s.id not in known:
                        before=[list(p) for p in s.points]
                        db.add(TemplateMigrationItem(migration_id=m.id,specimen_id=s.id,collection_id=c.id,status=IS.PENDING,before_points=before,after_points=remap_points(before,m.point_mapping),source_specimen_version=s.template_version,source_specimen_revision=s.revision))
                        known.add(s.id)
            db.flush()
            for it in list_items(db,m.id):
                if it.status==IS.APPLIED:continue
                s=db.get(ShapeSpecimen,it.specimen_id)
                if s is None:
                    it.status=IS.FAILED;it.message='裁片已不存在';raise _Conflict()
                # Version + revision tokens protect corrections made during the window.
                if s.template_version!=it.source_specimen_version or s.revision!=it.source_specimen_revision:
                    it.status=IS.STALE;it.message='迁移期间裁片被更正，需要追齐';raise _Conflict()
                current_before=[list(p) for p in s.points]
                after=remap_points(current_before,m.point_mapping)
                it.before_points=current_before;it.after_points=after
                s.points=after;s.template_version=to_v.version
                it.status=IS.APPLIED;it.message=''
            # All specimens remapped: flip the single active version atomically.
            for v in db.scalars(select(TemplateVersion).where(TemplateVersion.template_id==m.template_id)).all():
                v.is_active=(v.id==to_v.id)
            m.status=MS.COMPLETED;m.finished_at=datetime.utcnow();m.summary=_summary(db,m)
    except _Conflict:
        db.rollback();_mark_conflict(db,get_migration(db,m.id),'存在迁移期间更正或新增后未追齐的裁片')
        raise HTTPException(409,'存在迁移期间更正的裁片，切换已中止；请逐份追齐后再激活')
    except HTTPException:
        db.rollback();raise
    except Exception as exc:
        db.rollback()
        fresh=get_migration(db,m.id)
        if fresh.status==MS.IN_PROGRESS:_mark_conflict(db,fresh,str(exc)[:300])
        raise HTTPException(500,'切换执行中断，可在恢复后重新激活，已更正裁片不会被覆盖')
    return get_migration(db,m.id)

def rebase_item(db,migration_id,item_id,actor:str=''):
    m=get_migration(db,migration_id)
    if m.status in TERMINAL_STATUSES:raise HTTPException(409,'改版任务已结束，不能再追齐')
    it=db.get(TemplateMigrationItem,item_id)
    if not it or it.migration_id!=m.id:raise HTTPException(404,'受影响裁片记录不存在')
    s=db.get(ShapeSpecimen,it.specimen_id)
    if not s:raise HTTPException(404,'裁片已不存在')
    # Re-derive the remap from the specimen's CURRENT points and stamp both
    # tokens, so a correction made during the window is carried forward, never
    # overwritten by the stale preview coordinates.
    it.before_points=[list(p) for p in s.points]
    it.after_points=remap_points(it.before_points,m.point_mapping)
    it.source_specimen_version=s.template_version
    it.source_specimen_revision=s.revision
    it.status=IS.PENDING;it.message=''
    # Recalculate AFTER this item is cleared so the last catch-up can reopen
    # the migration for activation instead of leaving it stuck in conflict.
    remaining=[x for x in list_items(db,m.id) if x.status in (IS.FAILED,IS.STALE)]
    if not remaining and m.status==MS.CONFLICT:m.status=MS.DRAFT
    m.summary=_summary(db,m);db.commit()
    return it
def cancel_migration(db,migration_id,actor:str=''):
    m=get_migration(db,migration_id)
    if m.status not in (MS.DRAFT,MS.CONFLICT,MS.IN_PROGRESS):raise HTTPException(409,'已结束的改版任务不能取消')
    if m.status==MS.IN_PROGRESS:raise HTTPException(409,'切换执行中，请等待本次激活结束后再处理冲突')
    m.status=MS.CANCELLED;m.finished_at=datetime.utcnow();m.summary=_summary(db,m);db.commit()
    return m

class _Conflict(Exception):
    pass
