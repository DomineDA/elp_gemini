"""일반 사용자 상단 메뉴 링크가 살아 있는 경로만 가리키는지 검사 (#166)."""

from __future__ import annotations

import re
from typing import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models.users import User
from app.rate_limit import limiter

USER_PASSWORD = "test-password-1234"
HTML = {"Accept": "text/html"}


@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(db_engine):
    return async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )


@pytest_asyncio.fixture
async def normal_user(session_factory) -> User:
    from app.services.auth_service import AuthService

    async with session_factory() as session:
        user = User(
            username="testuser",
            nickname="testuser",
            hashed_password=AuthService.hash_password(USER_PASSWORD),
            is_admin=False,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


@pytest_asyncio.fixture
async def http_client(
    session_factory, monkeypatch
) -> AsyncIterator[AsyncClient]:
    async def _get_db_override() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    # HTML 요청은 미들웨어가 자체 세션 팩토리로 사용자를 검증한다.
    monkeypatch.setattr(
        "app.middleware.auth_middleware.async_session_maker", session_factory
    )
    app.dependency_overrides[get_db] = _get_db_override
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        yield client
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture(autouse=True)
def _no_rate_limit():
    limiter.reset()
    original = limiter.enabled
    limiter.enabled = False
    yield
    limiter.enabled = original
    limiter.reset()


async def _login(client: AsyncClient) -> None:
    resp = await client.post(
        "/auth/login/user",
        data={"user_id": "testuser", "password": USER_PASSWORD},
        follow_redirects=False,
    )
    assert resp.status_code in (200, 302)


def _nav(html: str) -> str:
    nav = re.search(r"<nav\b.*?</nav>", html, flags=re.DOTALL)
    assert nav, "상단 <nav> 없음"
    return nav.group(0)


# /dashboard는 nav_links 블록을 덮어써서 base.html 사용자 메뉴가 안 보인다.
# 메뉴를 그대로 상속하는 사용자 페이지로 검사한다.
MENU_PAGE = "/simulation/setup"


async def test_user_menu_points_to_dashboard_only(http_client, normal_user):
    await _login(http_client)

    resp = await http_client.get(MENU_PAGE, headers=HTML)
    assert resp.status_code == 200
    nav = _nav(resp.text)
    assert 'href="/dashboard/upload"' not in nav
    assert 'href="/dashboard/viewer"' not in nav
    assert "문서 뷰어" not in nav
    assert 'href="/dashboard"' in nav


async def test_every_user_menu_link_resolves(http_client, normal_user):
    await _login(http_client)
    resp = await http_client.get(MENU_PAGE, headers=HTML)

    hrefs = re.findall(r'href="([^"]+)"', _nav(resp.text))
    assert hrefs
    for href in hrefs:
        got = await http_client.get(href, headers=HTML, follow_redirects=False)
        assert got.status_code in (200, 302), (href, got.status_code)
