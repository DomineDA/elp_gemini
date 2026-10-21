"""#182: 프롬프트 관리 화면에 지어낸 버전·활성·생성일을 표시하지 않는다."""

from fastapi.testclient import TestClient

from app.dependencies import get_current_admin
from app.main import app
from app.models.users import User

client = TestClient(app)


def test_admin_prompts_page_hides_fake_metadata():
    admin = User(id=1, username="admin", nickname="Admin", is_admin=True)
    app.dependency_overrides[get_current_admin] = lambda: admin
    try:
        response = client.get("/admin/prompts")
    finally:
        app.dependency_overrides.pop(get_current_admin, None)

    assert response.status_code == 200
    body = response.text
    assert "버전 " not in body
    assert ">활성</span>" not in body
    assert "생성: " not in body
    assert 'data-content-id="prompt-content-qna"' in body
    assert 'id="prompt-content-qna"' in body
