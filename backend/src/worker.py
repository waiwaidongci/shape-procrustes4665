import time
from pathlib import Path
from sqlalchemy import select
from redis import Redis
from src.config.database import Session
from src.config.settings import REDIS_URL
from src.models import AlignmentRun,TemplateMigration
from src.constants.enums import RunStatus,MigrationStatus
from src.services.run_service import execute_run
from src.services.migration_service import activate_migration
redis=Redis.from_url(REDIS_URL)
while True:
    Path('/tmp/heartbeat').touch()
    with Session() as db:
        # Interrupted activation recovery: DB is authoritative, Redis only wakes.
        stuck=db.scalar(select(TemplateMigration).where(TemplateMigration.status==MigrationStatus.IN_PROGRESS).order_by(TemplateMigration.id))
        if stuck:
            try:activate_migration(db,stuck.id)
            except Exception:pass
        r=db.scalar(select(AlignmentRun).where(AlignmentRun.status.in_([RunStatus.QUEUED,RunStatus.RUNNING])).order_by(AlignmentRun.id))
        if r:execute_run(db,r.id)
        else:
            # Wake on either queue; short timeout keeps recovery scans responsive.
            queued=redis.brpop(['shapes:runs','shapes:migrations'],timeout=2)
            if queued and queued[1].decode().isdigit() and queued[0]==b'shapes:migrations':
                mid=int(queued[1]);m=db.get(TemplateMigration,mid)
                if m and m.status in (MigrationStatus.IN_PROGRESS,MigrationStatus.DRAFT,MigrationStatus.CONFLICT):
                    try:activate_migration(db,mid)
                    except Exception:pass
    time.sleep(.1)
