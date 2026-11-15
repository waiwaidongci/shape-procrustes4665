from pydantic import BaseModel,Field,ConfigDict
from src.schemas.template import Outline,Label

class MigrationCreate(BaseModel):
    name:str=Field(min_length=2,max_length=140)
    template_id:int
    # New revision payload (immutable once published as a version).
    labels:list[Label]=Field(min_length=8,max_length=8)
    points:Outline
    convention:str=Field(default='',max_length=1200)
    # Bijections on homologous labels: source label -> destination label, 8 entries.
    label_mapping:dict[str,str]=Field(min_length=8,max_length=8)
    @property
    def labels_unique_ok(self)->bool:
        return len(set(self.labels))==8

class MigrationItemOut(BaseModel):
    id:int
    migration_id:int
    specimen_id:int
    collection_id:int
    status:str
    before_points:list
    after_points:list
    source_specimen_version:int
    source_specimen_revision:int
    message:str
    specimen_code:str=''
    specimen_name:str=''
    collection_code:str=''
    model_config=ConfigDict(from_attributes=True)

class MigrationOut(BaseModel):
    id:int
    name:str
    template_id:int
    from_version_id:int
    to_version_id:int
    from_version:int
    to_version:int
    status:str
    label_mapping:dict
    point_mapping:list
    summary:dict
    created_by:str
    created_at:object=None
    updated_at:object=None
    finished_at:object=None
    model_config=ConfigDict(from_attributes=True)

class MigrationDetailOut(MigrationOut):
    items:list[MigrationItemOut]=[]
