from sqlalchemy import select,func
from fastapi import HTTPException
from src.models import ShapeSpecimen
from src.services.collection_service import get_collection
from src.services.template_service import active_version

def list_specimens(db,collection_id):return db.scalars(select(ShapeSpecimen).where(ShapeSpecimen.collection_id==collection_id).order_by(ShapeSpecimen.code)).all()

def save(db,data,id=None):
    c=get_collection(db,data.collection_id)
    current_version=active_version(db,c.template_id).version
    if db.scalar(select(ShapeSpecimen).where(ShapeSpecimen.collection_id==data.collection_id,ShapeSpecimen.code==data.code,ShapeSpecimen.id!=(id or 0))):raise HTTPException(409,'集合内裁片编号重复')
    s=db.get(ShapeSpecimen,id) if id else ShapeSpecimen()
    if id and not s:raise HTTPException(404,'裁片不存在')
    if id and s.collection_id!=data.collection_id:raise HTTPException(422,'不能迁移既有裁片所属集合')
    if not id and db.scalar(select(func.count()).select_from(ShapeSpecimen).where(ShapeSpecimen.collection_id==data.collection_id))>=120:raise HTTPException(422,'每集合最多120份裁片')
    if id:
        # Optimistic freshness: a page opened against an older template version
        # must not overwrite coordinates already remapped to a newer version.
        if data.template_version!=s.template_version:
            raise HTTPException(409,f'裁片对应模板已改版（当前v{s.template_version}）或已被他人更正，页面数据已过期，请重载后按当前角点顺序编辑')
    else:
        # New specimens always bind to the active version; client value ignored.
        s.template_version=current_version;s.revision=1
    s.collection_id=data.collection_id;s.code=data.code;s.name=data.name;s.points=data.points;s.source_note=data.source_note
    if id:s.revision=(s.revision or 1)+1  # every correction advances the revision token
    db.add(s);db.commit();return s

def create_specimen(db,data):return save(db,data)
def update_specimen(db,id,data):return save(db,data,id)
