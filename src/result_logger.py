"""날짜별 CSV 로그 파일 기록 모듈."""
import csv
import datetime
from pathlib import Path

FIELDS = ["time", "email", "code", "stage", "error_type", "message", "result"]


def write_result(base_dir: Path, log_type: str, entry: dict) -> None:
    """날짜별 CSV 파일에 실행 결과 한 줄 기록.

    log_type: "픽" or "보너스"
    entry keys: time, email, code, stage, error_type, message, result
    """
    try:
        logs_dir = base_dir / "logs"
        logs_dir.mkdir(exist_ok=True)
        today = datetime.date.today().strftime("%Y-%m-%d")
        path = logs_dir / f"{log_type}_{today}.csv"
        is_new = not path.exists()
        with open(path, "a", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            if is_new:
                writer.writeheader()
            row = {k: entry.get(k, "") for k in FIELDS}
            writer.writerow(row)
    except Exception:
        pass


def classify_exception(e: Exception) -> tuple[str, str]:
    """예외 → (stage, error_type) 분류."""
    err_str = str(e)
    err_lower = err_str.lower()
    if "429" in err_str or "too many" in err_lower or "frequent" in err_lower:
        return "코드 제출", "사이트 차단(429)"
    if "timeout" in err_lower or "timed out" in err_lower:
        return "알 수 없음", "타임아웃"
    if "network" in err_lower or "connection" in err_lower or "eof" in err_lower or "refused" in err_lower:
        return "연결", "네트워크 오류"
    return "알 수 없음", type(e).__name__
