from src.services import migration_service as service
from src.models import ShapeSpecimen,ShapeCollection,TemplateVersion

def _item_payload(db,it):
    s=db.get(ShapeSpecimen,it.specimen_id);c=db.get(ShapeCollection,it.collection_id)
    return {
        'id':it.id,'migration_id':it.migration_id,'specimen_id':it.specimen_id,'collection_id':it.collection_id,
        'status':it.status,'before_points':it.before_points,'after_points':it.after_points,
        'source_specimen_version':it.source_specimen_version,'source_specimen_revision':it.source_specimen_revision,'message':it.message,
        'specimen_code':s.code if s else '','specimen_name':s.name if s else '',
        'collection_code':c.code if c else '',
    }

def _migration_payload(db,m,include_items=False):
    from_v=db.get(TemplateVersion,m.from_version_id)
    to_v=db.get(TemplateVersion,m.to_version_id)
    payload={
        'id':m.id,'name':m.name,'template_id':m.template_id,'from_version_id':m.from_version_id,'to_version_id':m.to_version_id,
        'from_version':from_v.version,'to_version':to_v.version,'status':m.status,
        'label_mapping':m.label_mapping,'point_mapping':m.point_mapping,'summary':m.summary,
        'created_by':m.created_by,'created_at':m.created_at,'updated_at':m.updated_at,'finished_at':m.finished_at,
    }
    if include_items:payload['items']=[_item_payload(db,it) for it in service.list_items(db,m.id)]
    return payload

def index(db):return [_migration_payload(db,m) for m in service.list_migrations(db)]
def detail(db,id):return _migration_payload(db,service.get_migration(db,id),include_items=True)
def create(db,data,user):return _migration_payload(db,service.create_migration(db,data,user.email),include_items=True)
def activate(db,id,user):return _migration_payload(db,service.activate_migration(db,id,user.email),include_items=True)
def rebase(db,id,item_id,user):
    service.rebase_item(db,id,item_id,user.email);return _migration_payload(db,service.get_migration(db,id),include_items=True)
def cancel(db,id,user):return _migration_payload(db,service.cancel_migration(db,id,user.email))
