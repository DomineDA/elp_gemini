"""
사용자 산출물(uploads/·reports/)이 /static 으로 공개되지 않는지 검증 (#168).
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import Base
from app.dependencies import get_current_user, get_db
from app.main import app
from app.models.users import User


@pytest_asyncio.fixture
async def session_factory(tmp_path):
    db_path = tmp_path / "t.db"
    eng = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(eng, expire_on_commit=False)
    yield factory
    await eng.dispose()


@pytest_asyncio.fixture
async def client(session_factory, tmp_path, monkeypatch):
    from app.routers import views as views_mod

    real_path_cls = views_mod.Path

    def _patched_path(*args, **kwargs):
        p = real_path_cls(*args, **kwargs)
        if str(p) == "app/static/uploads":
            return real_path_cls(str(tmp_path / "uploads"))
        return p

    monkeypatch.setattr(views_mod, "Path", _patched_path)

    async with session_factory() as s:
        users = [
            User(username=n, nickname=n, hashed_password="x")
            for n in ("alice", "bob")
        ]
        s.add_all(users)
        await s.commit()
        ids = [u.id for u in users]

    current = {"id": ids[0]}

    async def override_get_user():
        async with session_factory() as s:
            return (
                await s.execute(select(User).where(User.id == current["id"]))
            ).scalar_one()

    async def override_get_db():
        async with session_factory() as s:
            yield s

    app.dependency_overrides[get_current_user] = override_get_user
    app.dependency_overrides[get_db] = override_get_db

    owner_dir = tmp_path / "uploads" / str(ids[0])
    owner_dir.mkdir(parents=True)
    (owner_dir / "a.pdf").write_bytes(b"%PDF-1.4 test\n%%EOF\n")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, current, ids

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def anon_client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
@pytest.mark.parametrize("rel", ["uploads/1/x.pdf", "reports/1/x.md"])
async def test_static_user_files_are_404_without_login(
    rel, anon_client, tmp_path, monkeypatch
):
    # StaticFiles 는 요청 시 cwd 기준으로 경로를 찾으므로, 실제 파일이
    # 존재하는 tmp cwd 에서 요청해야 차단 여부를 확인할 수 있다.
    target = tmp_path / "app" / "static" / rel
    target.parent.mkdir(parents=True)
    target.write_bytes(b"secret")
    (tmp_path / "app" / "static" / "js").mkdir()
    monkeypatch.chdir(tmp_path)

    async with anon_client as c:
        res = await c.get(f"/static/{rel}")
    assert res.status_code == 404
    assert b"secret" not in res.content


@pytest.mark.asyncio
async def test_static_js_still_served(anon_client):
    async with anon_client as c:
        res = await c.get("/static/js/pdf_viewer.js")
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_owner_can_fetch_upload(client):
    c, _, _ = client
    res = await c.get("/dashboard/uploads/a.pdf")
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert res.content.startswith(b"%PDF-1.4")


@pytest.mark.asyncio
async def test_owner_can_fetch_filename_with_consecutive_dots(client, tmp_path):
    # 업로드 sanitizer 는 점을 유지하므로 basename 안의 ".." 는 정상 파일명이다.
    c, _, ids = client
    name = "20261021_lesson..pdf"
    (tmp_path / "uploads" / str(ids[0]) / name).write_bytes(b"%PDF-1.4 x\n")
    res = await c.get(f"/dashboard/uploads/{name}")
    assert res.status_code == 200
    assert res.content.startswith(b"%PDF-1.4")


@pytest.mark.asyncio
async def test_other_user_gets_404(client):
    c, current, ids = client
    current["id"] = ids[1]
    res = await c.get("/dashboard/uploads/a.pdf")
    assert res.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    # 리터럴 ".." 는 클라이언트(httpx·브라우저)가 /dashboard/ 로 정규화해
    # 이 라우트에 닿지 않으므로 인코딩된 형태로 검사한다.
    [
        "/dashboard/uploads/%2e%2e",
        "/dashboard/uploads/..%2F2%2Fa.pdf",
        "/dashboard/uploads/%2e%2e%5c2%5ca.pdf",
    ],
)
async def test_traversal_is_404(client, path):
    c, _, _ = client
    res = await c.get(path)
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_anonymous_json_request_is_401(anon_client):
    async with anon_client as c:
        res = await c.get(
            "/dashboard/uploads/a.pdf",
            headers={"Accept": "application/json"},
        )
    assert res.status_code == 401
