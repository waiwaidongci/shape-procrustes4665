from sqlalchemy import select
from fastapi import HTTPException
from src.models import Template,TemplateVersion,ShapeSpecimen

OPEN_STATUSES=('draft','in_progress','conflict')

def list_templates(db):
    templates=db.scalars(select(Template).order_by(Template.id)).all()
    for t in templates:
        t.current_version=active_version_no(db,t.id)
    return templates

def get_template(db,id):
    t=db.get(Template,id)
    if not t:raise HTTPException(404,'同源模板不存在')
    return t

def active_version(db,template_id):
    v=db.scalar(select(TemplateVersion).where(TemplateVersion.template_id==template_id,TemplateVersion.is_active.is_(True)))
    if not v:raise HTTPException(409,'模板尚未发布任何版本，请先完成版本引导')
    return v

def active_version_no(db,template_id):
    v=db.scalar(select(TemplateVersion.version).where(TemplateVersion.template_id==template_id,TemplateVersion.is_active.is_(True)))
    return v if v is not None else 1

def list_versions(db,template_id):
    get_template(db,template_id)
    return db.scalars(select(TemplateVersion).where(TemplateVersion.template_id==template_id).order_by(TemplateVersion.version)).all()

def _next_version_no(db,template_id):
    top=db.scalar(select(TemplateVersion.version).where(TemplateVersion.template_id==template_id).order_by(TemplateVersion.version.desc()))
    return (top or 0)+1

def create_template(db,data,actor=''):
    if db.scalar(select(Template).where(Template.code==data.code)):raise HTTPException(409,'模板编号重复')
    t=Template(code=data.code,name=data.name,labels=data.labels,points=data.points,convention=data.convention)
    db.add(t);db.flush()
    db.add(TemplateVersion(template_id=t.id,version=1,labels=data.labels,points=data.points,convention=data.convention,is_active=True,created_by=actor))
    db.commit();t.current_version=1;return t

def update_template(db,id,data):
    t=get_template(db,id)
    if db.scalar(select(Template).where(Template.code==data.code,Template.id!=id)):raise HTTPException(409,'模板编号重复')
    v=active_version(db,id)
    # Labels/points define homologous correspondence; changing them in place would
    # silently misread every existing specimen. A versioned migration is required.
    if data.labels!=v.labels or [list(map(float,p)) for p in data.points]!= [list(map(float,p)) for p in v.points]:
        raise HTTPException(422,'角点标签或参考坐标调整必须通过“模板改版”发布新版本，不能直接覆盖当前版本')
    t.code=data.code;t.name=data.name;t.convention=data.convention
    v.convention=data.convention
    db.commit();t.current_version=v.version;return t

def bootstrap_versions(db):
    """Idempotent first-run guide: every legacy template gets an active v1, specimens stamp v1."""
    for t in db.scalars(select(Template)).all():
        exists=db.scalar(select(TemplateVersion.id).where(TemplateVersion.template_id==t.id))
        if not exists:
            db.add(TemplateVersion(template_id=t.id,version=1,labels=t.labels,points=t.points,convention=t.convention,is_active=True,created_by='system-bootstrap'))
    db.commit()
    # Backfill any specimen missing the freshness token.
    db.execute(ShapeSpecimen.__table__.update().where(ShapeSpecimen.template_version.is_(None)).values(template_version=1))
    db.commit()
