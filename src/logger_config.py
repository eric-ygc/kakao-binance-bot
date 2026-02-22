"""
UTF-8 로거 설정.
Windows cp949 콘솔 환경에서 한글 깨짐 방지를 위해
파일 핸들러와 콘솔 핸들러 모두 UTF-8로 설정.
"""
import io
import logging
import sys
from pathlib import Path


def setup_logger(name: str, log_file: str = "logs/kakao_monitor.log") -> logging.Logger:
    """
    UTF-8 파일 핸들러 + UTF-8 콘솔 핸들러가 붙은 로거 반환.
    동일 name으로 중복 호출해도 핸들러가 중복 추가되지 않는다.
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # UTF-8 파일 핸들러
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # UTF-8 콘솔 핸들러 (Windows cp949 환경 대응)
    try:
        utf8_stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
        )
        console_handler = logging.StreamHandler(utf8_stdout)
    except AttributeError:
        # stdout.buffer가 없는 환경 (IDLE 등)
        console_handler = logging.StreamHandler(sys.stdout)

    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 루트 로거로의 전파 차단 (중복 출력 방지)
    logger.propagate = False

    return logger
