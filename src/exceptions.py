"""공유 예외 클래스."""


class AutoCancelled(Exception):
    """중지 버튼으로 자동 입력이 취소됐을 때 발생."""


class LoginFailed(Exception):
    """이메일/비밀번호 오류로 로그인에 실패했을 때 발생."""


class InvalidParameter(Exception):
    """Confirm 후 Invalid parameter 팝업이 감지됐을 때 발생."""
