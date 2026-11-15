from enum import StrEnum
class Role(StrEnum):
    ADMIN='admin'; ANALYST='analyst'; VIEWER='viewer'
class RunStatus(StrEnum):
    QUEUED='queued'; RUNNING='running'; COMPLETED='completed'; FAILED='failed'
class NoteStatus(StrEnum):
    DRAFT='draft'; APPROVED='approved'; REJECTED='rejected'
class MigrationStatus(StrEnum):
    DRAFT='draft'; IN_PROGRESS='in_progress'; CONFLICT='conflict'; COMPLETED='completed'; CANCELLED='cancelled'
class MigrationItemStatus(StrEnum):
    PENDING='pending'; APPLIED='applied'; FAILED='failed'; STALE='stale'
