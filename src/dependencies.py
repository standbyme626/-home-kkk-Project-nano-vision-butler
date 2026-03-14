"""Dependency injection and lightweight service layer for FastAPI routes."""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, is_dataclass
from typing import Any, Generator

from fastapi import Depends, Request

from src.db.repositories.audit_repo import AuditRepo
from src.db.repositories.device_repo import DeviceRepo
from src.db.repositories.event_repo import EventRepo
from src.db.repositories.media_repo import MediaRepo
from src.db.repositories.observation_repo import ObservationRepo
from src.db.repositories.ocr_repo import OcrRepo
from src.db.repositories.state_repo import StateRepo
from src.db.repositories.telegram_update_repo import TelegramUpdateRepo
from src.mcp_server.server import create_server
from src.security.security_guard import SecurityGuard
from src.services.device_service import DeviceService as DeviceCoreService
from src.services.memory_service import MemoryService
from src.services.ocr_service import OCRService
from src.services.policy_service import PolicyService as PolicyCoreService
from src.services.perception_service import PerceptionService
from src.services.reply_builder import TelegramReplyBuilder
from src.services.reply_service import TelegramReplyService
from src.services.state_service import StateService as StateCoreService
from src.settings import AppConfig


def api_success(data: Any = None, message: str = "ok") -> dict[str, Any]:
    return {"ok": True, "message": message, "data": serialize(data)}


def api_error(code: str, message: str, details: Any = None) -> dict[str, Any]:
    return {
        "ok": False,
        "error": {"code": code, "message": message, "details": serialize(details)},
    }


def serialize(value: Any) -> Any:
    if value is None:
        return None
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, sqlite3.Row):
        return dict(value)
    if isinstance(value, list):
        return [serialize(item) for item in value]
    if isinstance(value, tuple):
        return [serialize(item) for item in value]
    if isinstance(value, dict):
        return {str(k): serialize(v) for k, v in value.items()}
    return value


class MemoryQueryService:
    def __init__(self, observation_repo: ObservationRepo, event_repo: EventRepo):
        self._observation_repo = observation_repo
        self._event_repo = event_repo

    def recent_events(
        self,
        *,
        zone_id: str | None,
        object_name: str | None,
        start_time: str | None,
        end_time: str | None,
        limit: int,
    ) -> list[Any]:
        return self._event_repo.query_recent_events(
            zone_id=zone_id,
            object_name=object_name,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
        )

    def last_seen(
        self,
        *,
        object_name: str,
        camera_id: str | None,
        zone_id: str | None,
    ) -> Any:
        return self._observation_repo.get_last_seen(
            object_name=object_name,
            camera_id=camera_id,
            zone_id=zone_id,
        )


class StateQueryService:
    def __init__(
        self,
        *,
        state_repo: StateRepo,
        observation_repo: ObservationRepo,
        conn: sqlite3.Connection,
        config: AppConfig,
    ):
        self._service = StateCoreService(
            state_repo=state_repo,
            observation_repo=observation_repo,
            conn=conn,
            config=config,
        )

    def object_state(
        self,
        *,
        object_name: str,
        camera_id: str | None,
        zone_id: str | None,
    ) -> Any:
        return self._service.get_object_state(
            object_name=object_name,
            camera_id=camera_id,
            zone_id=zone_id,
        )

    def zone_state(self, *, camera_id: str, zone_id: str) -> Any:
        return self._service.get_zone_state(camera_id=camera_id, zone_id=zone_id)

    def world_state(self, camera_id: str | None = None) -> dict[str, Any]:
        return self._service.get_world_state(camera_id=camera_id)


class PolicyService:
    def __init__(self, state_service: StateQueryService, device_repo: DeviceRepo, config: AppConfig):
        self._service = PolicyCoreService(
            state_service=state_service._service,
            device_repo=device_repo,
            config=config,
        )

    def evaluate_staleness(
        self,
        *,
        object_name: str,
        camera_id: str | None,
        zone_id: str | None,
        query_text: str | None = None,
        query_type: str | None = None,
    ) -> dict[str, Any]:
        return self._service.evaluate_staleness_for_object(
            object_name=object_name,
            camera_id=camera_id,
            zone_id=zone_id,
            query_text=query_text,
            query_type=query_type,
        )


class DeviceService:
    def __init__(self, core_service: DeviceCoreService, perception_service: PerceptionService):
        self._core_service = core_service
        self._perception_service = perception_service

    def get_status(self, device_id: str) -> Any:
        return self._core_service.get_device_status(device_id)

    def command_take_snapshot(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._core_service.take_snapshot(payload)

    def command_get_recent_clip(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._core_service.get_recent_clip(payload)

    def ingest_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._perception_service.ingest_event(payload)

    def heartbeat(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._perception_service.heartbeat(payload)


def get_app_config(request: Request) -> AppConfig:
    return request.app.state.settings


def get_db_connection(request: Request) -> Generator[sqlite3.Connection, None, None]:
    session_factory = request.app.state.session_factory
    with session_factory.connect() as conn:
        yield conn


def get_memory_service(conn: sqlite3.Connection = Depends(get_db_connection)) -> MemoryQueryService:
    return MemoryQueryService(observation_repo=ObservationRepo(conn), event_repo=EventRepo(conn))


def get_state_service(
    conn: sqlite3.Connection = Depends(get_db_connection),
    config: AppConfig = Depends(get_app_config),
) -> StateQueryService:
    return StateQueryService(
        state_repo=StateRepo(conn),
        observation_repo=ObservationRepo(conn),
        conn=conn,
        config=config,
    )


def get_policy_service(
    conn: sqlite3.Connection = Depends(get_db_connection),
    config: AppConfig = Depends(get_app_config),
) -> PolicyService:
    state_service = StateQueryService(
        state_repo=StateRepo(conn),
        observation_repo=ObservationRepo(conn),
        conn=conn,
        config=config,
    )
    return PolicyService(
        state_service=state_service,
        device_repo=DeviceRepo(conn),
        config=config,
    )


def get_device_service(
    conn: sqlite3.Connection = Depends(get_db_connection),
    config: AppConfig = Depends(get_app_config),
) -> DeviceService:
    device_repo = DeviceRepo(conn)
    media_repo = MediaRepo(conn)
    audit_repo = AuditRepo(conn)
    security_guard = SecurityGuard(
        config=config,
        audit_repo=audit_repo,
        device_repo=device_repo,
        media_repo=media_repo,
    )
    memory_service = MemoryService(
        observation_repo=ObservationRepo(conn),
        event_repo=EventRepo(conn),
        config=config,
    )
    ocr_service = OCRService(
        media_repo=media_repo,
        observation_repo=ObservationRepo(conn),
        event_repo=EventRepo(conn),
        ocr_repo=OcrRepo(conn),
        audit_repo=audit_repo,
    )
    perception_service = PerceptionService(
        device_repo=device_repo,
        audit_repo=audit_repo,
        memory_service=memory_service,
        config=config,
        security_guard=security_guard,
        ocr_service=ocr_service,
    )
    core_service = DeviceCoreService(
        device_repo=device_repo,
        media_repo=media_repo,
        audit_repo=audit_repo,
        config=config,
    )
    return DeviceService(core_service=core_service, perception_service=perception_service)


def get_ocr_service(conn: sqlite3.Connection = Depends(get_db_connection)) -> OCRService:
    return OCRService(
        media_repo=MediaRepo(conn),
        observation_repo=ObservationRepo(conn),
        event_repo=EventRepo(conn),
        ocr_repo=OcrRepo(conn),
        audit_repo=AuditRepo(conn),
    )


def get_telegram_reply_service(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db_connection),
    config: AppConfig = Depends(get_app_config),
) -> TelegramReplyService:
    config_dir = getattr(request.app.state, "config_dir", None)
    security_guard = SecurityGuard(
        config=config,
        audit_repo=AuditRepo(conn),
        device_repo=DeviceRepo(conn),
        media_repo=MediaRepo(conn),
    )
    return TelegramReplyService(
        update_repo=TelegramUpdateRepo(conn),
        mcp_server=create_server(config_dir=config_dir),
        config=config,
        reply_builder=TelegramReplyBuilder(),
        security_guard=security_guard,
    )
