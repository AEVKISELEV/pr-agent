from functools import partial
import copy
from jinja2 import Environment, StrictUndefined

from pr_agent.algo.ai_handlers.base_ai_handler import BaseAiHandler
from pr_agent.algo.ai_handlers.litellm_ai_handler import LiteLLMAIHandler
from pr_agent.algo.pr_processing import get_pr_diff
from pr_agent.algo.token_handler import TokenHandler
from pr_agent.config_loader import get_settings
from pr_agent.log import get_logger
from pr_agent.tools.pr_architecture_review import PRArchitectureReview


class PRArchitectureReviewDebug(PRArchitectureReview):
    """Return the architecture review prompt without calling the AI."""

    def __init__(self, pr_url: str, args: list | None = None,
                 ai_handler: partial[BaseAiHandler,] = LiteLLMAIHandler):
        super().__init__(pr_url, args=args, ai_handler=ai_handler)

    async def run(self):
        if not self.git_provider.get_files():
            get_logger().info(f"PR has no files: {self.pr_url}, skipping review")
            return None

        model = get_settings().config.model
        self.patches_diff = get_pr_diff(
            self.git_provider,
            self.token_handler,
            model,
            add_line_numbers_to_hunks=True,
            disable_extra_lines=False,
        )
        if not self.patches_diff:
            get_logger().warning(f"Empty diff for PR: {self.pr_url}")
            return None

        variables = copy.deepcopy(self.vars)
        variables["diff"] = self.patches_diff
        environment = Environment(undefined=StrictUndefined)
        system_prompt = environment.from_string(
            get_settings().pr_review_prompt.system
        ).render(variables)
        user_prompt = environment.from_string(
            get_settings().pr_review_prompt.user
        ).render(variables)

        prompt = (
            "**System Prompt**\n```\n" + system_prompt + "\n```\n\n" +
            "**User Prompt**\n```\n" + user_prompt + "\n```"
        )

        if get_settings().config.publish_output:
            self.git_provider.publish_comment(prompt)
        else:
            get_logger().info("Architecture review prompt", artifacts={"prompt": prompt})

        return prompt
