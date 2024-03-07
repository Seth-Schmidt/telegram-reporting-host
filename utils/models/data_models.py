import time
from enum import Enum
from pydantic import BaseModel
from typing import Optional
from typing import List


class RedisConfig(BaseModel):
    host: str
    port: int
    db: int
    password: Optional[str]


class TelegramConfig(BaseModel):
    bot_token: str
    telegram_endpoint: str
    message_timeout: int = 600


class RLimit(BaseModel):
    file_descriptors: int


class IssueReportingService(BaseModel):
    host: str
    port: str
    keepalive_secs: int
    keys_ttl: int = 86400
    gunicorn_workers: int = 20


class SettingsConf(BaseModel):
    telegram: TelegramConfig
    rate_limit: str
    redis: RedisConfig
    rlimit: RLimit
    issue_reporting_service: IssueReportingService


class ProjectStatus(BaseModel):
    projectId: str
    successfulSubmissions: int = 0
    incorrectSubmissions: int = 0
    missedSubmissions: int = 0


class SnapshotterStatus(BaseModel):
    totalSuccessfulSubmissions: int = 0
    totalIncorrectSubmissions: int = 0
    totalMissedSubmissions: int = 0
    consecutiveMissedSubmissions: int = 0
    projects: List[ProjectStatus]


class SnapshotterIssue(BaseModel):
    instanceID: str
    issueType: str
    projectID: str
    epochId: str
    timeOfReporting: str
    extra: Optional[str] = ''


class TelegramSnapshotterReportMessage(BaseModel):
    chatId: int
    slotId: int
    issue: SnapshotterIssue
    status: SnapshotterStatus


class EpochProcessingIssue(BaseModel):
    instanceID: str
    issueType: str
    timeOfReporting: str
    extra: Optional[str] = ''


class TelegramEpochProcessingReportMessage(BaseModel):
    chatId: int
    slotId: int
    issue: EpochProcessingIssue


class TelegramMessagePayload(BaseModel):
    chat_id: int
    text: str
    parse_mode: str = 'HTML'


class AuthCheck(BaseModel):
    authorized: bool = False
    api_key: str
    reason: str = ''


class RateLimitAuthCheck(AuthCheck):
    rate_limit_passed: bool = False
    retry_after: int = 1
    violated_limit: str
    current_limit: str


class UserStatusEnum(str, Enum):
    active = 'active'
    inactive = 'inactive'


class SnapshotterMetadata(BaseModel):
    rate_limit: str
    active: UserStatusEnum
    callsCount: int = 0
    throttledCount: int = 0
    next_reset_at: int = int(time.time()) + 86400
    name: str
    email: str
    alias: str
    uuid: Optional[str] = None