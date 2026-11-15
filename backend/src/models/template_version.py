from datetime import datetime
from sqlalchemy import String,ForeignKey,UniqueConstraint,DateTime,JSON,Boolean,Index,text
from sqlalchemy.orm import Mapped,mapped_column
from src.config.database import Base

# At most one active version per template. Partial unique indexes on both
# supported dialects: inactive (historical) versions are unrestricted, only one
# active row may exist per template. The service layer remains the authority.
_active_index=Index(
    'uq_template_active','template_id',unique=True,
    postgresql_where=text('is_active'),sqlite_where=text('is_active'),
)

class TemplateVersion(Base):
    """Immutable published version of a shared template; only one is active per template."""
    __tablename__='template_versions'
    id:Mapped[int]=mapped_column(primary_key=True)
    template_id:Mapped[int]=mapped_column(ForeignKey('templates.id'))
    version:Mapped[int]=mapped_column()
    labels:Mapped[list]=mapped_column(JSON)
    points:Mapped[list]=mapped_column(JSON)
    convention:Mapped[str]=mapped_column(String(1200),default='')
    is_active:Mapped[bool]=mapped_column(Boolean,default=False,index=True)
    created_by:Mapped[str]=mapped_column(String(160),default='')
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
    __table_args__=(
        UniqueConstraint('template_id','version',name='uq_template_version_no'),
        _active_index,
    )
