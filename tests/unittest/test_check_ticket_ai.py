from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pr_agent.tools.check_ticket import PRCheckTicket


@pytest.fixture(autouse=True)
def bugtracker_env(monkeypatch):
    monkeypatch.setenv("BUGTRACKER_URL", "https://bugs")


@pytest.fixture
def mock_git_provider():
    provider = MagicMock()
    provider.get_commit_messages.return_value = "core: 123: fix bug"
    provider.publish_comment = MagicMock()
    provider.get_pr_id.return_value = 1
    provider.pr = MagicMock()
    provider.pr.title = "t"
    return provider


@pytest.fixture
def mock_ai_handler():
    handler = MagicMock()
    handler.chat_completion = AsyncMock(return_value=("solved: true", "stop"))
    return handler


@pytest.mark.asyncio
async def test_check_ticket_ai_solved(mock_git_provider, mock_ai_handler):
    with patch("pr_agent.tools.check_ticket.get_git_provider", return_value=lambda url: mock_git_provider), \
         patch("pr_agent.tools.check_ticket.get_pr_diff", return_value="diff"), \
         patch("pr_agent.tools.check_ticket.requests.get") as mock_req, \
         patch("pr_agent.tools.check_ticket.get_settings") as mock_settings:

        resp = MagicMock()
        resp.json.return_value = {"description": "bug"}
        mock_req.return_value = resp

        mock_settings.return_value.pr_check_ticket_prompt.system = "sys"
        mock_settings.return_value.pr_check_ticket_prompt.user = "user"
        mock_settings.return_value.config.model = "gpt"
        mock_settings.return_value.config.temperature = 0.0
        mock_settings.return_value.config.publish_output = True

        tool = PRCheckTicket("url", ai_handler=lambda: mock_ai_handler)
        msg = await tool.run()

        assert "решена" in msg
        mock_git_provider.publish_comment.assert_called_once()


@pytest.mark.asyncio
async def test_check_ticket_ai_not_solved(mock_git_provider, mock_ai_handler):
    mock_ai_handler.chat_completion = AsyncMock(return_value=("solved: false", "stop"))
    with patch("pr_agent.tools.check_ticket.get_git_provider", return_value=lambda url: mock_git_provider), \
         patch("pr_agent.tools.check_ticket.get_pr_diff", return_value="diff"), \
         patch("pr_agent.tools.check_ticket.requests.get") as mock_req, \
         patch("pr_agent.tools.check_ticket.get_settings") as mock_settings:

        resp = MagicMock()
        resp.json.return_value = {"description": "bug"}
        mock_req.return_value = resp

        mock_settings.return_value.pr_check_ticket_prompt.system = "sys"
        mock_settings.return_value.pr_check_ticket_prompt.user = "user"
        mock_settings.return_value.config.model = "gpt"
        mock_settings.return_value.config.temperature = 0.0
        mock_settings.return_value.config.publish_output = True

        tool = PRCheckTicket("url", ai_handler=lambda: mock_ai_handler)
        msg = await tool.run()

        assert "не решена" in msg
        mock_git_provider.publish_comment.assert_called_once()

