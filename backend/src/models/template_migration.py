from datetime import datetime
from sqlalchemy import String,ForeignKey,UniqueConstraint,DateTime,JSON,Index,text
from sqlalchemy.orm import Mapped,mapped_column
from src.config.database import Base

class TemplateMigration(Base):
    """One template revision published across every collection sharing the template."""
    __tablename__='template_migrations'
    id:Mapped[int]=mapped_column(primary_key=True)
    name:Mapped[str]=mapped_column(String(140),unique=True)
    template_id:Mapped[int]=mapped_column(ForeignKey('templates.id'))
    from_version_id:Mapped[int]=mapped_column(ForeignKey('template_versions.id'))
    to_version_id:Mapped[int]=mapped_column(ForeignKey('template_versions.id'))
    status:Mapped[str]=mapped_column(String(20),default='draft')
    label_mapping:Mapped[dict]=mapped_column(JSON,default=dict)
    point_mapping:Mapped[list]=mapped_column(JSON,default=list)
    summary:Mapped[dict]=mapped_column(JSON,default=dict)
    created_by:Mapped[str]=mapped_column(String(160),default='')
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
    updated_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow,onupdate=datetime.utcnow)
    finished_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True,default=None)
    __table_args__=(
        Index('uq_template_open_migration','template_id',unique=True,
              postgresql_where=text("status IN ('draft','in_progress','conflict')"),
              sqlite_where=text("status IN ('draft','in_progress','conflict')")),
    )

class TemplateMigrationItem(Base):
    """Per-specimen point remap row; before/after snapshots drive preview and catch-up."""
    __tablename__='template_migration_items'
    id:Mapped[int]=mapped_column(primary_key=True)
    migration_id:Mapped[int]=mapped_column(ForeignKey('template_migrations.id'))
    specimen_id:Mapped[int]=mapped_column(ForeignKey('shape_specimens.id'))
    collection_id:Mapped[int]=mapped_column(ForeignKey('shape_collections.id'))
    status:Mapped[str]=mapped_column(String(20),default='pending')
    before_points:Mapped[list]=mapped_column(JSON,default=list)
    after_points:Mapped[list]=mapped_column(JSON,default=list)
    source_specimen_version:Mapped[int]=mapped_column(default=1)
    source_specimen_revision:Mapped[int]=mapped_column(default=1)
    message:Mapped[str]=mapped_column(String(600),default='')
    __table_args__=(UniqueConstraint('migration_id','specimen_id',name='uq_migration_specimen'),)
