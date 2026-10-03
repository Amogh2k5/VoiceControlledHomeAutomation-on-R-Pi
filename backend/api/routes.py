from datetime import datetime
from typing import Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from backend.core import HomeController, ModeManager, InputMode, CommandResult, ExecutionType
from backend.core.controller import APPLIANCE_REGISTRY, VALID_ACTIONS, ApplianceType
from backend.database import Database, CommandHistoryEntry, ScheduledCommand, get_database, close_database
from backend.scheduler import CommandScheduler, get_scheduler, close_scheduler
from backend.hardware import create_hardware
from backend.input import VoiceInput, VoskLiveListener, get_vosk_live_listener, close_vosk_live_listener
from backend.config import config
import logging

logger = logging.getLogger(__name__)


class ModeRequest(BaseModel):
    mode: str

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        valid = [m.value for m in InputMode]
        if v.lower() not in valid:
            raise ValueError(f"Invalid mode. Must be one of: {valid}")
        return v.lower()


class ModeResponse(BaseModel):
    mode: str
    valid_modes: List[str]


class ApplianceStateResponse(BaseModel):
    appliance: str
    state: str
    type: str


class StatusResponse(BaseModel):
    status: str
    mode: str
    appliances: List[ApplianceStateResponse]
    timestamp: str


class ApplianceControlRequest(BaseModel):
    appliance: str
    action: str
    delay_minutes: Optional[int] = None
    delay_seconds: Optional[int] = None

    @field_validator("appliance")
    @classmethod
    def validate_appliance(cls, v: str) -> str:
        if v not in APPLIANCE_REGISTRY:
            raise ValueError(f"Unknown appliance: {v}. Valid: {list(APPLIANCE_REGISTRY.keys())}")
        return v

    @field_validator("action")
    @classmethod
    def validate_action(cls, v: str) -> str:
        if v not in VALID_ACTIONS:
            raise ValueError(f"Invalid action: {v}. Must be one of: {list(VALID_ACTIONS)}")
        return v

    @field_validator("delay_minutes", "delay_seconds", mode="before")
    @classmethod
    def validate_delays(cls, v):
        if v is not None and v <= 0:
            raise ValueError("Delay must be greater than 0")
        return v


class ApplianceControlResponse(BaseModel):
    success: bool
    appliance: str
    action: str
    execution_type: str
    delay_minutes: Optional[int]
    delay_seconds: Optional[int]
    message: str
    scheduled_time: Optional[str] = None


class HistoryEntryResponse(BaseModel):
    id: int
    timestamp: str
    source: str
    appliance: str
    action: str
    delay_minutes: Optional[int]
    success: bool
    message: str
    execution_type: str


class HistoryResponse(BaseModel):
    history: List[HistoryEntryResponse]
    total: int
    limit: int
    offset: int


class ScheduledCommandResponse(BaseModel):
    id: int
    appliance: str
    action: str
    scheduled_time: str
    status: str
    created_at: str


class ScheduledCommandsResponse(BaseModel):
    schedules: List[ScheduledCommandResponse]
    total: int


# Global instances
_controller: Optional[HomeController] = None
_mode_manager: Optional[ModeManager] = None
_scheduler: Optional[CommandScheduler] = None
_database: Optional[Database] = None
_voice_input: Optional[VoiceInput] = None
_vosk_live_listener: Optional[VoskLiveListener] = None


def get_controller() -> HomeController:
    global _controller
    if _controller is None:
        _controller = HomeController(hardware=create_hardware())
    return _controller


def get_mode_manager() -> ModeManager:
    global _mode_manager
    if _mode_manager is None:
        _mode_manager = ModeManager()
    return _mode_manager


def get_db() -> Database:
    global _database
    if _database is None:
        _database = get_database()
    return _database


def get_scheduler_instance() -> CommandScheduler:
    global _scheduler
    if _scheduler is None:
        controller = get_controller()
        db = get_db()
        _scheduler = get_scheduler(controller, db)
        if not _scheduler.is_running():
            _scheduler.start()
    return _scheduler


def get_voice_input() -> VoiceInput:
    global _voice_input
    if _voice_input is None:
        _voice_input = VoiceInput(test_mode=True)
    return _voice_input


def get_vosk_live_listener() -> VoskLiveListener:
    global _vosk_live_listener
    if _vosk_live_listener is None:
        controller = get_controller()
        _vosk_live_listener = VoskLiveListener(controller=controller)
    return _vosk_live_listener


def shutdown_services():
    global _scheduler, _database, _voice_input, _vosk_live_listener
    close_scheduler()
    close_database()
    if _voice_input:
        _voice_input.close()
    if _vosk_live_listener:
        _vosk_live_listener.stop()
    _scheduler = None
    _database = None
    _voice_input = None
    _vosk_live_listener = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Home Automation API")
    get_scheduler_instance()
    
    # Detect test mode from environment
    import os
    test_mode = os.getenv("TESTING", "false").lower() == "true" or os.getenv("PYTEST_CURRENT_TEST") is not None
    
    if config.voice.enabled and not test_mode:
        logger.info("[VOICE] Initializing live voice listener...")
        listener = get_vosk_live_listener()
        listener.start()
    elif test_mode:
        logger.info("[VOICE] Test mode: live listener disabled")
    else:
        logger.info("[VOICE] Voice control disabled (VOICE_ENABLED=false)")
    yield
    logger.info("Shutting Down Home Automation API")
    shutdown_services()


app = FastAPI(
    title="Home Automation API",
    description="REST API for Raspberry Pi Home Automation System",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8080", "http://127.0.0.1:3000", "http://127.0.0.1:8080", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/status", response_model=StatusResponse)
async def get_status(
    controller: HomeController = Depends(get_controller),
    mode_manager: ModeManager = Depends(get_mode_manager),
):
    states = controller.get_all_states()
    appliances = [
        ApplianceStateResponse(
            appliance=appliance,
            state=state,
            type=APPLIANCE_REGISTRY[appliance].value,
        )
        for appliance, state in states.items()
    ]
    return StatusResponse(
        status="running",
        mode=mode_manager.get_mode_str(),
        appliances=appliances,
        timestamp=datetime.now().isoformat(),
    )


@app.get("/mode", response_model=ModeResponse)
async def get_mode(mode_manager: ModeManager = Depends(get_mode_manager)):
    return ModeResponse(
        mode=mode_manager.get_mode_str(),
        valid_modes=mode_manager.get_valid_modes(),
    )


@app.post("/mode", response_model=ModeResponse)
async def set_mode(
    request: ModeRequest,
    mode_manager: ModeManager = Depends(get_mode_manager),
):
    try:
        mode_manager.set_mode(request.mode)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return ModeResponse(
        mode=mode_manager.get_mode_str(),
        valid_modes=mode_manager.get_valid_modes(),
    )


@app.get("/appliances", response_model=List[ApplianceStateResponse])
async def get_appliances(controller: HomeController = Depends(get_controller)):
    states = controller.get_all_states()
    return [
        ApplianceStateResponse(
            appliance=appliance,
            state=state,
            type=APPLIANCE_REGISTRY[appliance].value,
        )
        for appliance, state in states.items()
    ]


@app.post("/appliance", response_model=ApplianceControlResponse)
async def control_appliance(
    request: ApplianceControlRequest,
    controller: HomeController = Depends(get_controller),
    scheduler: CommandScheduler = Depends(get_scheduler_instance),
    db: Database = Depends(get_db),
):
    from backend.input.models import InputCommand

    delay_minutes = request.delay_minutes or 0
    delay_seconds = request.delay_seconds or 0

    has_delay = delay_minutes > 0 or delay_seconds > 0
    controller_delay = delay_minutes if delay_minutes > 0 else None

    cmd = InputCommand(
        appliance=request.appliance,
        action=request.action,
        delay_minutes=controller_delay,
    )

    result = controller.execute(cmd)

    scheduled_time = None
    final_delay_minutes = None
    final_delay_seconds = None

    if has_delay:
        if delay_minutes > 0:
            sched_id = scheduler.schedule_command(
                request.appliance,
                request.action,
                delay_minutes=delay_minutes,
            )
            sched = db.get_scheduled_command(sched_id)
            if sched:
                scheduled_time = sched.scheduled_time
            final_delay_minutes = delay_minutes
        elif delay_seconds > 0:
            sched_id = scheduler.schedule_command(
                request.appliance,
                request.action,
                delay_minutes=0,
                delay_seconds=delay_seconds,
            )
            sched = db.get_scheduled_command(sched_id)
            if sched:
                scheduled_time = sched.scheduled_time
            final_delay_seconds = delay_seconds
        
        if result.execution_type != ExecutionType.SCHEDULED:
            result = CommandResult(
                success=result.success,
                appliance=result.appliance,
                action=result.action,
                execution_type=ExecutionType.SCHEDULED,
                delay_minutes=delay_minutes if delay_minutes > 0 else None,
                message=f"Command scheduled for {delay_minutes} minutes" if delay_minutes > 0 else f"Command scheduled for {delay_seconds} seconds",
                scheduled_time=scheduled_time,
            )
    else:
        db.log_command("api", cmd, result)

    return ApplianceControlResponse(
        success=result.success,
        appliance=result.appliance,
        action=result.action,
        execution_type=result.execution_type.value,
        delay_minutes=final_delay_minutes,
        delay_seconds=final_delay_seconds,
        message=result.message,
        scheduled_time=scheduled_time,
    )


@app.get("/history", response_model=HistoryResponse)
async def get_history(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    appliance: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    db: Database = Depends(get_db),
):
    if appliance and appliance not in APPLIANCE_REGISTRY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown appliance: {appliance}. Valid: {list(APPLIANCE_REGISTRY.keys())}"
        )

    history = db.get_command_history(
        limit=limit,
        offset=offset,
        appliance=appliance,
        source=source,
    )

    return HistoryResponse(
        history=[
            HistoryEntryResponse(
                id=entry.id,
                timestamp=entry.timestamp,
                source=entry.source,
                appliance=entry.appliance,
                action=entry.action,
                delay_minutes=entry.delay_minutes,
                success=entry.success,
                message=entry.message,
                execution_type=entry.execution_type,
            )
            for entry in history
        ],
        total=len(history),
        limit=limit,
        offset=offset,
    )


@app.get("/schedules", response_model=ScheduledCommandsResponse)
async def get_schedules(
    scheduler: CommandScheduler = Depends(get_scheduler_instance),
):
    pending = scheduler.get_pending()
    return ScheduledCommandsResponse(
        schedules=[
            ScheduledCommandResponse(
                id=cmd.id,
                appliance=cmd.appliance,
                action=cmd.action,
                scheduled_time=cmd.scheduled_time,
                status=cmd.status,
                created_at=cmd.created_at,
            )
            for cmd in pending
        ],
        total=len(pending),
    )


@app.delete("/schedules/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_schedule(
    schedule_id: int,
    scheduler: CommandScheduler = Depends(get_scheduler_instance),
):
    sched = scheduler.get_scheduled_command(schedule_id)
    if not sched:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scheduled command {schedule_id} not found",
        )
    if sched.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel command with status: {sched.status}",
        )
    scheduler.cancel_command(schedule_id)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


def create_app() -> FastAPI:
    return app


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)