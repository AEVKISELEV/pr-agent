from functools import partial

from pr_agent.algo.ai_handlers.base_ai_handler import BaseAiHandler
from pr_agent.algo.ai_handlers.litellm_ai_handler import LiteLLMAIHandler
from pr_agent.algo.token_handler import TokenHandler
from pr_agent.config_loader import get_settings
from pr_agent.log import get_logger
from pr_agent.tools.pr_reviewer import PRReviewer


class PRArchitectureReview(PRReviewer):
    """Review pull request with additional architecture context."""

    def __init__(self, pr_url: str, args: list | None = None,
                 ai_handler: partial[BaseAiHandler,] = LiteLLMAIHandler):
        custom_path = None
        cleaned_args = []
        for arg in args or []:
            if arg.startswith("--custom-context="):
                custom_path = arg.split("=", 1)[1].strip().strip('"').strip("'")
            else:
                cleaned_args.append(arg)

        super().__init__(pr_url, args=cleaned_args, ai_handler=ai_handler)

        base_path = "ARHITECTURE.md"
        branch = "master"

        base_content = ""
        try:
            base_content = self.git_provider.get_pr_file_content(base_path, branch)
        except Exception as e:
            get_logger().warning(
                f"Failed to load architecture file {base_path}: {e}"
            )

        custom_content = ""
        if custom_path:
            try:
                custom_content = self.git_provider.get_pr_file_content(custom_path, branch)
            except Exception as e:
                get_logger().warning(
                    f"Failed to load custom architecture file {custom_path}: {e}"
                )

        if base_content or custom_content:
            extra = self.vars.get("extra_instructions", "") or ""
            if base_content:
                extra += (
                    f"\n\nProject architecture context from {base_path}:\n"
                    f"{base_content}\n"
                )
            if custom_content:
                extra += (
                    f"\n\nAdditional architecture context from {custom_path}:\n"
                    f"{custom_content}\n"
                )
            self.vars["extra_instructions"] = extra
            self.token_handler = TokenHandler(
                self.git_provider.pr,
                self.vars,
                get_settings().pr_review_prompt.system,
                get_settings().pr_review_prompt.user,
            )
