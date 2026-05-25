import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta

from criba.filters.account_age import AccountAgeFilter


@pytest.mark.asyncio
async def test_new_account(make_post):
    filter = AccountAgeFilter()
    now = datetime.now(timezone.utc)
    post = make_post(author_created_at=now - timedelta(days=3))
    context = {}
    result = await filter.apply(post, context)
    assert result.score == 0.8
    assert result.flagged is True
    assert result.metadata["account_age_days"] == 3
    assert result.metadata["account_is_new"] is True


@pytest.mark.asyncio
async def test_suspicious_account(make_post):
    filter = AccountAgeFilter()
    now = datetime.now(timezone.utc)
    post = make_post(author_created_at=now - timedelta(days=15))
    context = {}
    result = await filter.apply(post, context)
    assert result.score == 0.5
    assert result.flagged is False
    assert result.metadata["account_age_days"] == 15
    assert result.metadata["account_is_new"] is False


@pytest.mark.asyncio
async def test_mature_account(make_post):
    filter = AccountAgeFilter()
    now = datetime.now(timezone.utc)
    post = make_post(author_created_at=now - timedelta(days=100))
    context = {}
    result = await filter.apply(post, context)
    assert result.score == 0.0
    assert result.flagged is False
    assert result.metadata["account_age_days"] == 100
    assert result.metadata["account_is_new"] is False


@pytest.mark.asyncio
async def test_no_creation_date(make_post):
    filter = AccountAgeFilter()
    post = make_post(author_created_at=None)
    context = {}
    result = await filter.apply(post, context)
    assert result.score == 0.0
    assert result.flagged is False
    assert result.metadata["account_age_days"] is None


@pytest.mark.asyncio
async def test_moderate_account(make_post):
    filter = AccountAgeFilter()
    now = datetime.now(timezone.utc)
    post = make_post(author_created_at=now - timedelta(days=60))
    context = {}
    result = await filter.apply(post, context)
    assert result.score == 0.2
    assert result.flagged is False
    assert result.metadata["account_age_days"] == 60


@pytest.mark.asyncio
async def test_exactly_new_account_threshold(make_post):
    filter = AccountAgeFilter()
    now = datetime.now(timezone.utc)
    post = make_post(author_created_at=now - timedelta(days=7))
    context = {}
    result = await filter.apply(post, context)
    assert result.score == 0.8
    assert result.flagged is True