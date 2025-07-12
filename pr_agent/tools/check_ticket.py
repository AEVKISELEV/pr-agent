import json
import os
import re
from functools import partial

import requests
from jinja2 import Environment, StrictUndefined
from typing import Tuple

from pr_agent.algo.ai_handlers.base_ai_handler import BaseAiHandler
from pr_agent.algo.ai_handlers.litellm_ai_handler import LiteLLMAIHandler
from pr_agent.algo.pr_processing import get_pr_diff
from pr_agent.algo.token_handler import TokenHandler
from pr_agent.algo.utils import load_yaml
from pr_agent.config_loader import get_settings
from pr_agent.git_providers import get_git_provider
from pr_agent.log import get_logger


class PRCheckTicket:
    """Custom command to validate bug ticket resolution in a commit."""

    TICKET_PATTERN = re.compile(r"([\w_]+):\s*(\d+):\s*", re.IGNORECASE)

    def __init__(self, pr_url: str, args=None,
                 ai_handler: partial[BaseAiHandler,] = LiteLLMAIHandler):
        self.git_provider = get_git_provider()(pr_url)
        self.ai_handler = ai_handler()
        self.pr_url = pr_url

        self.vars = {
            "ticket_description": "",
            "commit_message": "",
            "diff": "",
        }

    def _load_bugtracker_url(self) -> str:
        """Load bug tracker base URL from environment variables."""
        env_keys = [
            "BUGTRACKER_URL",
            "BUGTRACKER.URL",
            "BUGTRACKER__URL",
        ]
        for key in env_keys:
            value = os.getenv(key)
            if value:
                return value
        return ""

    @staticmethod
    def _extract_ticket_id(commit_message: str) -> Tuple[str, str]:
        match = PRCheckTicket.TICKET_PATTERN.search(commit_message)
        if match:
            return match.group(1), match.group(2)
        return "", ""


    def _load_last_commit_message(self) -> str:
        messages = self.git_provider.get_commit_messages()
        if not messages:
            return ""
        lines = [line.strip() for line in messages.splitlines() if line.strip()]
        if not lines:
            return ""
        last = lines[-1]
        last = re.sub(r"^\d+\.\s*", "", last)
        return last

    def _get_pr_diff(self) -> str:
        token_handler = TokenHandler()
        model = get_settings().config.model
        try:
            diff = get_pr_diff(
                self.git_provider,
                token_handler,
                model,
                add_line_numbers_to_hunks=True,
                disable_extra_lines=False,
            )
            return diff or ""
        except Exception as e:
            get_logger().error(f"Failed to get diff: {e}")
            return ""


    async def _validate_with_ai(self, description: str, commit_message: str, diff: str) -> bool:
        """Use AI to check if the commit fixes the ticket."""
        self.vars.update(
            {
                "ticket_description": description,
                "commit_message": commit_message,
                "diff": diff,
            }
        )
        environment = Environment(undefined=StrictUndefined)
        system_prompt = environment.from_string(
            get_settings().pr_check_ticket_prompt.system
        ).render(self.vars)
        user_prompt = environment.from_string(
            get_settings().pr_check_ticket_prompt.user
        ).render(self.vars)
        
        if get_settings().config.publish_output:
            self.git_provider.publish_comment(user_prompt)
            
        try:
            response, _ = await self.ai_handler.chat_completion(
                model=get_settings().config.model,
                temperature=get_settings().config.temperature,
                system=system_prompt,
                user=user_prompt,
            )
            if get_settings().config.publish_output:
                self.git_provider.publish_comment(response)
            
            data = load_yaml(response.strip())
            
            if get_settings().config.publish_output:
                self.git_provider.publish_comment(data)

            solved_value = str(data.get("solved", "")).lower() if isinstance(data, dict) else ""
            return solved_value in {"yes", "true", "1"}
        except Exception as e:
            get_logger().error(f"AI validation failed: {e}")
            return False

    async def run(self):
        commit_message = self._load_last_commit_message()
        module, ticket_id = self._extract_ticket_id(commit_message)
        bugtracker_url = self._load_bugtracker_url()
        if not ticket_id:
            message = f"\u2139\ufe0f Не найдено ID тикета в описании коммита {commit_message} -> {bugtracker_url}"
            if get_settings().config.publish_output:
                self.git_provider.publish_comment(message)
            return message


        if not bugtracker_url:
            message = f"⚠️ BUGTRACKER_URL не найден для тикета {ticket_id}"
            if get_settings().config.publish_output:
                self.git_provider.publish_comment(message)
            return message

        try:
            resp = requests.get(
                f"{bugtracker_url.rstrip('/')}/rest.php",
                params={"action": "get_ticket_by_id", "id": ticket_id},
                timeout=10,
            )
            data = resp.json()
        except Exception as e:
            get_logger().error(f"Failed to fetch ticket {ticket_id}: {e}")
            message = f"⚠️ Не удалось получить данные тикета {ticket_id} URL: {resp.url} Ответ (raw): {resp.text}"
            if get_settings().config.publish_output:
                self.git_provider.publish_comment(message)
            return message

        description = data.get("description", "")
        diff = self._get_pr_diff()
        solved = await self._validate_with_ai(description, commit_message, diff)
        if solved:
            message = f"✅ Проблема из тикета {ticket_id} решена в этом коммите."
        else:
            message = f"⚠️ Проблема из тикета {ticket_id} не решена или не затронута в этом коммите."
        if get_settings().config.publish_output:
            self.git_provider.publish_comment(message)
        return message

