import pytest
import pytest_asyncio

from criba.filters.language import LanguageFilter


@pytest.mark.asyncio
async def test_primary_language_matches(make_post):
    filter = LanguageFilter(primary_language="es")
    post = make_post(content="Este es un mensaje de prueba en español")
    context = {"primary_language": "es"}
    result = await filter.apply(post, context)
    assert result.score == 0.0
    assert result.flagged is False
    assert result.metadata["language_detected"] == "es"
    assert result.metadata["language_matches_primary"] is True


@pytest.mark.asyncio
async def test_foreign_language_detected(make_post):
    filter = LanguageFilter(primary_language="es")
    post = make_post(content="This is an English message that should be detected")
    context = {"primary_language": "es"}
    result = await filter.apply(post, context)
    assert result.score > 0
    assert result.flagged is True
    assert result.metadata["language_detected"] == "en"
    assert result.metadata["language_matches_primary"] is False


@pytest.mark.asyncio
async def test_short_content(make_post):
    filter = LanguageFilter(primary_language="es")
    post = make_post(content="Short")
    context = {"primary_language": "es"}
    result = await filter.apply(post, context)
    assert result.score == 0.1
    assert result.flagged is False
    assert result.metadata["language_detected"] is None


@pytest.mark.asyncio
async def test_empty_content(make_post):
    filter = LanguageFilter(primary_language="es")
    post = make_post(content="")
    context = {"primary_language": "es"}
    result = await filter.apply(post, context)
    assert result.score == 0.1
    assert result.flagged is False
    assert result.metadata["language_detected"] is None


@pytest.mark.asyncio
async def test_default_primary_language(make_post):
    filter = LanguageFilter()
    post = make_post(content="Este es un mensaje de prueba en español")
    context = {}
    result = await filter.apply(post, context)
    assert result.score == 0.0
    assert result.metadata["language_matches_primary"] is True