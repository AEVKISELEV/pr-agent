import copy
from functools import partial

from jinja2 import Environment, StrictUndefined

from pr_agent.algo.ai_handlers.base_ai_handler import BaseAiHandler
from pr_agent.algo.ai_handlers.litellm_ai_handler import LiteLLMAIHandler
from pr_agent.algo.pr_processing import get_pr_diff, retry_with_fallback_models
from pr_agent.algo.token_handler import TokenHandler
from pr_agent.config_loader import get_settings
from pr_agent.git_providers import get_git_provider_with_context
from pr_agent.log import get_logger


class PRCheckTests:
    def __init__(self, pr_url: str, args: list = None,
                 ai_handler: partial[BaseAiHandler,] = LiteLLMAIHandler):
        self.git_provider = get_git_provider_with_context(pr_url)
        self.ai_handler = ai_handler()
        self.pr_url = pr_url
        self.patches_diff = None
        self.prediction = None

        self.vars = {
            "title": self.git_provider.pr.title,
            "description": self.git_provider.get_pr_description(),
            "diff": "",
            "files_contents": "",
        }

        prompt_path = '.ai/pr-agent/prompt/check-tests.md'
        try:
            self.user_prompt_template = self.git_provider.get_pr_file_content(
                prompt_path, self.git_provider.get_pr_branch())
        except Exception:
            self.user_prompt_template = (
                "You are a software tester reviewing a pull request.\n"
                "Diff:\n{{ diff }}\n\nFiles:\n{{ files_contents }}\n"
                "Provide a bullet list of test scenarios that should be added."
            )

        self.system_prompt = "You are a code review assistant."  # simple system prompt

        self.token_handler = TokenHandler(
            self.git_provider.pr,
            self.vars,
            self.system_prompt,
            self.user_prompt_template,
        )

    async def run(self):
        try:
            if not self.git_provider.get_files():
                get_logger().info(f"PR has no files: {self.pr_url}, skipping check tests")
                return None

            get_logger().info("Generating test scenarios for PR...")
            if get_settings().config.publish_output:
                self.git_provider.publish_comment("Preparing test scenarios...", is_temporary=True)

            await retry_with_fallback_models(self._prepare_prediction)

            if self.prediction and get_settings().config.publish_output:
                self.git_provider.remove_initial_comment()
                self.git_provider.publish_comment(self.prediction)
        except Exception as e:
            get_logger().error(f"Error generating test scenarios: {e}")
        return None

    async def _prepare_prediction(self, model: str):
        self.patches_diff = get_pr_diff(self.git_provider, self.token_handler, model)
        files_contents = []
        try:
            diff_files = self.git_provider.get_diff_files()
            for file in diff_files:
                content = file.head_file or self.git_provider.get_pr_file_content(
                    file.filename, self.git_provider.get_pr_branch())
                if content:
                    files_contents.append(
                        f"\n==file name==\n\n{file.filename}\n\n==file content==\n\n{content}\n=========\n")
        except Exception as e:
            get_logger().warning(f"Failed collecting file contents: {e}")

        variables = copy.deepcopy(self.vars)
        variables["diff"] = self.patches_diff
        variables["files_contents"] = "".join(files_contents)
        environment = Environment(undefined=StrictUndefined)
        system_prompt = environment.from_string(self.system_prompt).render(variables)
        user_prompt = environment.from_string(self.user_prompt_template).render(variables)
        response, _ = await self.ai_handler.chat_completion(
            model=model,
            temperature=get_settings().config.temperature,
            system=system_prompt,
            user=user_prompt,
        )
        self.prediction = response
