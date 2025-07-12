import json
import re
from pathlib import Path
from functools import partial
from typing import List, Tuple

import requests

from pr_agent.config_loader import get_settings
from pr_agent.git_providers import get_git_provider
from pr_agent.algo.pr_processing import get_pr_diff
from pr_agent.algo.token_handler import TokenHandler
from pr_agent.log import get_logger


class PRCheckTicket:
    """Custom command to validate bug ticket resolution in a commit."""

    TICKET_PATTERN = re.compile(r"([\w_]+):\s*(\d+):\s*\[BUGS\]", re.IGNORECASE)
    LINE_PATTERN = re.compile(r"(?:line|строк[а]?)[\s:]*([0-9]+)(?:-([0-9]+))?", re.IGNORECASE)

    def __init__(self, pr_url: str, args=None, ai_handler: partial = None):
        self.git_provider = get_git_provider()(pr_url)
        self.pr_url = pr_url

    def _load_bugtracker_url(self) -> str:
        config_file = Path("config.qodo.json")
        if config_file.is_file():
            try:
                data = json.loads(config_file.read_text())
                return data.get("BUGTRACKER_URL", "")
            except Exception as e:
                get_logger().error(f"Failed to parse {config_file}: {e}")
        return ""

    @staticmethod
    def _extract_ticket_id(commit_message: str) -> Tuple[str, str]:
        match = PRCheckTicket.TICKET_PATTERN.search(commit_message)
        if match:
            return match.group(1), match.group(2)
        return "", ""

    @staticmethod
    def _extract_lines(description: str) -> List[Tuple[int, int]]:
        lines = []
        for m in PRCheckTicket.LINE_PATTERN.finditer(description):
            start = int(m.group(1))
            end = int(m.group(2) or start)
            lines.append((start, end))
        return lines

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

    @staticmethod
    def _diff_contains_lines(diff: str, lines: List[Tuple[int, int]]) -> bool:
        for start, end in lines:
            for n in range(start, end + 1):
                pattern = rf"^\s*{n}\s+[+-]"
                if re.search(pattern, diff, flags=re.MULTILINE):
                    return True
        return False

    async def run(self):
        commit_message = self._load_last_commit_message()
        module, ticket_id = self._extract_ticket_id(commit_message)
        if not ticket_id:
            message = "\u2139\ufe0f Не найдено ID тикета в описании коммита"
            if get_settings().config.publish_output:
                self.git_provider.publish_comment(message)
            return message

        bugtracker_url = self._load_bugtracker_url()
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
            message = f"⚠️ Не удалось получить данные тикета {ticket_id}"
            if get_settings().config.publish_output:
                self.git_provider.publish_comment(message)
            return message

        description = data.get("description", "")
        lines = self._extract_lines(description)
        diff = self._get_pr_diff()
        solved = bool(lines and diff and self._diff_contains_lines(diff, lines))
        if solved:
            message = f"✅ Проблема из тикета {ticket_id} решена в этом коммите."
        else:
            message = f"⚠️ Проблема из тикета {ticket_id} не решена или не затронута в этом коммите."
        if get_settings().config.publish_output:
            self.git_provider.publish_comment(message)
        return message

