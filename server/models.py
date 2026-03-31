"""SQLAlchemy 모델 정의"""
import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text

from .database import Base


class Computer(Base):
    __tablename__ = "computers"

    id = Column(String, primary_key=True)  # 사용자 지정 이름 (예: "PC-01")
    display_name = Column(String, default="")
    api_key = Column(String, nullable=False)  # 에이전트 인증용
    config_json = Column(Text, default="{}")
    bonus_config_json = Column(Text, default="{}")
    config_version = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow,
                        onupdate=datetime.datetime.utcnow)


class ComputerStatus(Base):
    __tablename__ = "computer_status"

    computer_id = Column(String, ForeignKey("computers.id", ondelete="CASCADE"),
                         primary_key=True)
    is_online = Column(Boolean, default=False)
    last_heartbeat = Column(DateTime, nullable=True)
    monitoring_active = Column(Boolean, default=False)
    auto_input_active = Column(Boolean, default=False)
    last_code = Column(String, default="")
    last_code_time = Column(DateTime, nullable=True)
    success_count = Column(Integer, default=0)
    fail_count = Column(Integer, default=0)
    app_version = Column(String, default="")
    account_count = Column(Integer, default=0)
    enabled_account_count = Column(Integer, default=0)
    agent_version = Column(String, default="")
    recent_logs = Column(Text, default="[]")


class Command(Base):
    __tablename__ = "commands"

    id = Column(Integer, primary_key=True, autoincrement=True)
    computer_id = Column(String, ForeignKey("computers.id", ondelete="CASCADE"))
    command_type = Column(String, nullable=False)  # start_monitor, stop_monitor, submit_code
    payload = Column(Text, default="{}")
    status = Column(String, default="pending")  # pending, acked, completed, failed
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)


class Screenshot(Base):
    __tablename__ = "screenshots"

    computer_id = Column(String, ForeignKey("computers.id", ondelete="CASCADE"),
                         primary_key=True)
    image_data = Column(Text, nullable=False)  # base64 PNG
    captured_at = Column(DateTime, default=datetime.datetime.utcnow)


class CodeLog(Base):
    __tablename__ = "code_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    computer_id = Column(String, ForeignKey("computers.id", ondelete="CASCADE"))
    code = Column(String, nullable=False)
    detected_at = Column(DateTime, default=datetime.datetime.utcnow)
    total_accounts = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    fail_count = Column(Integer, default=0)
