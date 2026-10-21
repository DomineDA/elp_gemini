"""관리자 QnA 로그 세션 필드 이스케이프 회귀 테스트 (#167)."""

import re
from pathlib import Path

TEMPLATE = Path("app/templates/admin/admin_qna_logs.html")

# session_id는 DB 정수, messages.map 안의 본문은 escapeHtml로 따로 감싼다.
ALLOWED_PREFIXES = (
    "escapeHtml(",
    "formatDate(",
    "getUserTypeBadgeClass(",
    "session.message_count",
    "session.session_id",
    "session.messages.map(",
)


def _source() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


def test_session_title_is_escaped():
    src = _source()
    assert "${escapeHtml(session.title || '제목 없음')}" in src
    assert "${session.title || '제목 없음'}" not in src


def test_no_raw_session_interpolation_in_inner_html():
    exprs = re.findall(r"\$\{\s*([^}]*session\.[^}]*)\}", _source())
    raw = [e for e in exprs if not e.strip().startswith(ALLOWED_PREFIXES)]
    assert raw == []
