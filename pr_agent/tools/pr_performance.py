import copy
from functools import partial

from jinja2 import Environment, StrictUndefined

from pr_agent.algo.ai_handlers.base_ai_handler import BaseAiHandler
from pr_agent.algo.ai_handlers.litellm_ai_handler import LiteLLMAIHandler
from pr_agent.algo.pr_processing import get_pr_diff, retry_with_fallback_models
from pr_agent.algo.token_handler import TokenHandler
from pr_agent.config_loader import get_settings
from pr_agent.git_providers import get_git_provider
from pr_agent.log import get_logger
from pr_agent.algo.utils import ModelType

class PRPerformanceReview:
    def __init__(self, pr_url: str, args: list = None,
                 ai_handler: partial[BaseAiHandler,] = LiteLLMAIHandler):
        self.git_provider = get_git_provider()(pr_url)
        self.ai_handler = ai_handler()
        self.pr_url = pr_url
        self.patches_diff = None
        self.prediction = None

        self.vars = {
            "title": self.git_provider.pr.title,
            "description": self.git_provider.get_pr_description(),
            "diff": "",
            "extra_instructions": get_settings().get("pr_performance", {}).get("extra_instructions", ""),
        }

        prompt_path = '.ai/pr-agent/prompt/PERFORMANCE.md'

        self.user_prompt_template = (
                "You are a performance reviewer for a pull request.\n"
                "Diff:\n{{ diff }}\n\n"
                "Provide a bullet list of performance issues and suggestions."
            )
        
        try:
            prompt = self.git_provider.get_pr_file_content(
                prompt_path, self.git_provider.get_pr_branch())
            
            if prompt:
                self.user_prompt_template = prompt
        except Exception as e:
            get_logger().debug(f"GET PROMPT", ERROR=e)

        self.system_prompt = "You are a code review assistant specializing in performance analysis."

        self.token_handler = TokenHandler(
            self.git_provider.pr,
            self.vars,
            self.system_prompt,
            self.user_prompt_template,
        )
        self.progress = "## Checking performance\n\n"
        self.progress += "\nWork in progress ...<br>\n<img src=\"https://codium.ai/images/pr_agent/dual_ball_loading-crop.gif\" width=48>"
        self.progress_response = None

    async def run(self):
        try:
            if not self.git_provider.get_files():
                get_logger().info(f"PR has no files: {self.pr_url}, skipping performance review")
                return None

            get_logger().info("Checking performance for PR...")
            if (get_settings().config.publish_output and get_settings().config.publish_output_progress
                    and not get_settings().config.get('is_auto_command', False)):
                if self.git_provider.is_supported("gfm_markdown"):
                    self.progress_response = self.git_provider.publish_comment(self.progress)
                else:
                    self.git_provider.publish_comment("Preparing performance review...", is_temporary=True)
            elif get_settings().config.publish_output:
                self.git_provider.publish_comment("Preparing performance review...", is_temporary=True)

            await retry_with_fallback_models(self._prepare_prediction, model_type=ModelType.REGULAR)

            if self.prediction and get_settings().config.publish_output:
                if self.progress_response:
                    self.git_provider.edit_comment(self.progress_response, body=self.prediction)
                else:
                    self.git_provider.remove_initial_comment()
                    self.git_provider.publish_comment(self.prediction)
        except Exception as e:
            get_logger().error(f"Error generating performance review: {e}")
            if self.progress_response:
                self.progress_response.delete()
            else:
                try:
                    self.git_provider.remove_initial_comment()
                except Exception:
                    pass
        return None

    async def _prepare_prediction(self, model: str):
        self.patches_diff = get_pr_diff(self.git_provider, self.token_handler, model)
        variables = copy.deepcopy(self.vars)
        variables["diff"] = self.patches_diff
        environment = Environment(undefined=StrictUndefined)
        system_prompt = environment.from_string(self.system_prompt).render(variables)
        user_prompt = environment.from_string(self.user_prompt_template).render(variables)

        get_logger().debug(f"GET Prediction", user_prompt=user_prompt)

        response, _ = await self.ai_handler.chat_completion(
            model=model,
            temperature=get_settings().config.temperature,
            system=system_prompt,
            user=user_prompt,
        )
        self.prediction = response
