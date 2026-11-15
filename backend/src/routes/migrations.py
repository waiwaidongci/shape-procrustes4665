from fastapi import APIRouter,Depends
from src.config.database import get_db
from src.utils.auth import current_user,editor
from src.schemas.migration import MigrationCreate,MigrationOut,MigrationDetailOut
from src.controllers import migration_controller as controller
router=APIRouter(prefix='/migrations',tags=['migrations'])
@router.get('',response_model=list[MigrationOut])
def index(db=Depends(get_db),user=Depends(current_user)):return controller.index(db)
@router.post('',response_model=MigrationDetailOut,status_code=201)
def create(data:MigrationCreate,db=Depends(get_db),user=Depends(editor)):return controller.create(db,data,user)
@router.get('/{id}',response_model=MigrationDetailOut)
def detail(id:int,db=Depends(get_db),user=Depends(current_user)):return controller.detail(db,id)
@router.post('/{id}/activate',response_model=MigrationDetailOut)
def activate(id:int,db=Depends(get_db),user=Depends(editor)):return controller.activate(db,id,user)
@router.post('/{id}/items/{item_id}/rebase',response_model=MigrationDetailOut)
def rebase(id:int,item_id:int,db=Depends(get_db),user=Depends(editor)):return controller.rebase(db,id,item_id,user)
@router.post('/{id}/cancel',response_model=MigrationOut)
def cancel(id:int,db=Depends(get_db),user=Depends(editor)):return controller.cancel(db,id,user)
