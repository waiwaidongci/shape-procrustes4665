from src.services import template_service as service
def index(db):return service.list_templates(db)
def versions(db,id):return service.list_versions(db,id)
def create(db,data,user):return service.create_template(db,data,user.email)

def update(db,id,data):return service.update_template(db,id,data)
