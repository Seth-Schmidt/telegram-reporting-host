import asyncio
import datetime
import uuid
from functools import wraps
from typing import Any
from typing import Dict
from typing import Optional
from web3 import Web3

import redis
from fastapi import Depends
from fastapi import FastAPI
from fastapi import Request
from fastapi import Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from httpx import AsyncClient

from settings.conf import settings

from auth.utils.data_models import RateLimitAuthCheck
from auth.utils.data_models import UserStatusEnum
from auth.utils.helpers import inject_rate_limit_fail_response
from auth.utils.helpers import rate_limit_auth_check
from utils.models.data_models import TelegramMessagePayload
from utils.models.data_models import TelegramEpochProcessingReportMessage
from utils.models.data_models import TelegramSnapshotterReportMessage
from utils.default_logger import logger
from utils.rate_limiter import load_rate_limiter_scripts
from utils.redis_keys import get_last_message_sent_key
from utils.redis_conn import RedisPool

service_logger = logger.bind(
    service='PowerLoom|TelegramMessagingService|ServiceEntry',
)


def acquire_bounded_semaphore(fn):
    @wraps(fn)
    async def wrapped(*args, **kwargs):
        sem: asyncio.BoundedSemaphore = kwargs['semaphore']
        await sem.acquire()
        result = None
        try:
            result = await fn(*args, **kwargs)
        except Exception as e:
            service_logger.opt(exception=True).error(
                f'Error in {fn.__name__}: {e}',
            )
            pass
        finally:
            sem.release()
            return result

    return wrapped


# setup CORS origins stuff
origins = ['*']

redis_lock = redis.Redis()

app = FastAPI()
app.logger = service_logger

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


@app.middleware('http')
async def request_middleware(request: Request, call_next: Any) -> Optional[Dict]:
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id

    with service_logger.contextualize(request_id=request_id):
        service_logger.info('Request started for: {}', request.url)
        try:
            response = await call_next(request)

        except Exception as ex:
            service_logger.opt(exception=True).error(f'Request failed: {ex}')

            response = JSONResponse(
                content={
                    'info':
                        {
                            'success': False,
                            'response': 'Internal Server Error',
                        },
                    'request_id': request_id,
                }, status_code=500,
            )

        finally:
            response.headers['X-Request-ID'] = request_id
            service_logger.info('Request ended')
            return response


@app.on_event('startup')
async def startup_boilerplate():
    app.state.aioredis_pool = RedisPool(writer_redis_conf=settings.redis)
    await app.state.aioredis_pool.populate()
    app.state.reader_redis_pool = app.state.aioredis_pool.reader_redis_pool
    app.state.writer_redis_pool = app.state.aioredis_pool.writer_redis_pool
    app.state.rate_limit_lua_script_shas = await load_rate_limiter_scripts(app.state.writer_redis_pool)
    app.state.async_client = AsyncClient()
    app.state.auth = dict()
    


@app.post('/reportSnapshotIssue')
async def notify_snapshotter_issue(
        request: Request,
        req_parsed: TelegramSnapshotterReportMessage,
        response: Response,
        rate_limit_auth_dep: RateLimitAuthCheck = Depends(
            rate_limit_auth_check,
        ),
):
    """
    Report issue from a snapshotter
    """
    if not (
            rate_limit_auth_dep.rate_limit_passed and
            rate_limit_auth_dep.authorized and
            rate_limit_auth_dep.owner.active == UserStatusEnum.active
    ):
        return inject_rate_limit_fail_response(rate_limit_auth_dep)

    try:
        snapshotter_id = Web3.to_checksum_address(req_parsed.issue.instanceID)
    except ValueError:
        return JSONResponse(status_code=400, content={'message': 'Invalid instanceID.'})
    
    else:
        time_of_reporting = int(float(req_parsed.issue.timeOfReporting))

        # set last last_message_timestamp if not already set and return the previous value
        # set value to expire after message_timeout seconds
        last_message_timestamp = await app.state.reader_redis_pool.set(
            name=get_last_message_sent_key(snapshotter_id),
            value=time_of_reporting,
            get=True,
            nx=True,
            ex=settings.telegram.message_timeout,
        )

        # Send message if last_message_timestamp is None or has expired after message_timeout seconds
        if not last_message_timestamp:
            time_of_reporting_formatted = datetime.datetime.fromtimestamp(time_of_reporting).strftime('%Y-%m-%d %H:%M:%S')
            snapshotter_id_masked = snapshotter_id[:6] + '*********************' + snapshotter_id[-6:]

            text = ("<b>Snapshotter failed to submit snapshot data:</b>\n"
                    f"<code>Instance Address: {snapshotter_id_masked}\n"
                    f"Slot ID: {req_parsed.slotId}\n"
                    f"Error Message: {req_parsed.issue.issueType}\n"
                    f"Error Details: {req_parsed.issue.extra}\n"
                    f"Total Missed Submissions: {req_parsed.status.totalMissedSubmissions}\n"
                    f"Consecutive Missed Submissions: {req_parsed.status.consecutiveMissedSubmissions}\n"
                    f"Reported At: {time_of_reporting_formatted}</code>")
            
            message_payload = TelegramMessagePayload(
                chat_id=req_parsed.chatId,
                text=text,
            )

            app.logger.info(message_payload.dict())
            
            resp = await app.state.async_client.post(
                f'{settings.telegram.telegram_endpoint}/bot{settings.telegram.bot_token}/sendMessage',
                data=message_payload.dict(),
            )

            if resp.status_code != 200:
                return JSONResponse(status_code=500, content={'message': 'Failed to send message.'})

            app.logger.info(resp.json())
    
    return JSONResponse(status_code=200, content={'message': 'Reported Issue.'})


@app.post('/reportEpochProcessingIssue')
async def notify_epoch_issue(
        request: Request,
        req_parsed: TelegramEpochProcessingReportMessage,
        response: Response,
        rate_limit_auth_dep: RateLimitAuthCheck = Depends(
            rate_limit_auth_check,
        ),
):
    """
    Report issue from a snapshotter
    """
    if not (
            rate_limit_auth_dep.rate_limit_passed and
            rate_limit_auth_dep.authorized and
            rate_limit_auth_dep.owner.active == UserStatusEnum.active
    ):
        return inject_rate_limit_fail_response(rate_limit_auth_dep)

    try:
        snapshotter_id = Web3.to_checksum_address(req_parsed.issue.instanceID)
    except ValueError:
        return JSONResponse(status_code=400, content={'message': 'Invalid instanceID.'})
    
    else:
        time_of_reporting = int(float(req_parsed.issue.timeOfReporting))

        # set last last_message_timestamp if not already set and return the previous value
        # set value to expire after message_timeout seconds
        last_message_timestamp = await app.state.reader_redis_pool.set(
            name=get_last_message_sent_key(snapshotter_id),
            value=time_of_reporting,
            get=True,
            nx=True,
            ex=settings.telegram.message_timeout,
        )

        # Send message if last_message_timestamp is None or has expired after message_timeout seconds
        if not last_message_timestamp:
            time_of_reporting_formatted = datetime.datetime.fromtimestamp(time_of_reporting).strftime('%Y-%m-%d %H:%M:%S')
            snapshotter_id_masked = snapshotter_id[:6] + '*********************' + snapshotter_id[-6:]

            text = ("<b>Snapshotter failed to complete epoch processing:</b>\n"
                    f"<code>Instance Address: {snapshotter_id_masked}\n"
                    f"Slot ID: {req_parsed.slotId}\n"
                    f"Error Message: {req_parsed.issue.issueType}\n"
                    f"Error Details: {req_parsed.issue.extra}\n"
                    f"Reported At: {time_of_reporting_formatted}</code>")
            
            message_payload = TelegramMessagePayload(
                chat_id=req_parsed.chatId,
                text=text,
            )

            app.logger.info(message_payload.dict())
            
            resp = await app.state.async_client.post(
                f'{settings.telegram.telegram_endpoint}/bot{settings.telegram.bot_token}/sendMessage',
                data=message_payload.dict(),
            )

            if resp.status_code != 200:
                return JSONResponse(status_code=500, content={'message': 'Failed to send message.'})

            app.logger.info(resp.json())
    
    return JSONResponse(status_code=200, content={'message': 'Reported Issue.'})