from pydantic import BaseModel,Field,ConfigDict
from src.schemas.template import Outline,Label

class SpecimenInput(BaseModel):
    collection_id:int
    code:str=Field(min_length=2,max_length=50,pattern=r'^[A-Za-z0-9_-]+$')
    name:str=Field(min_length=2,max_length=100)
    points:Outline
    source_note:str=Field(default='',max_length=300)
    # Freshness token: the template version the page read before editing.
    # Ignored on create (server stamps the active version); verified on update.
    template_version:int=Field(default=1,ge=1,strict=True)
class SpecimenOut(SpecimenInput):
    id:int
    revision:int=1
    model_config=ConfigDict(from_attributes=True)
