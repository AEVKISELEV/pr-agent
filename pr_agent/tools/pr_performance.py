import copy
from functools import partial

from pr_agent.algo.ai_handlers.base_ai_handler import BaseAiHandler
from pr_agent.algo.ai_handlers.litellm_ai_handler import LiteLLMAIHandler
from pr_agent.algo.pr_processing import get_pr_diff, retry_with_fallback_models
from pr_agent.algo.token_handler import TokenHandler
from pr_agent.config_loader import get_settings
from pr_agent.git_providers import get_git_provider
from pr_agent.git_providers.git_provider import get_main_pr_language
from pr_agent.log import get_logger


class PRPerformance:
    def __init__(self, pr_url: str, cli_mode=False, args: list = None,
                 ai_handler: partial[BaseAiHandler,] = LiteLLMAIHandler):
        self.git_provider = get_git_provider()(pr_url)
        self.main_language = get_main_pr_language(
            self.git_provider.get_languages(), self.git_provider.get_files()
        )
        self.ai_handler = ai_handler()
        self.ai_handler.main_pr_language = self.main_language
        self.patches_diff = None
        self.prediction = None
        self.cli_mode = cli_mode
        base_path = "PERFORMANCE.md"
        branch = get_settings().get("PR_HELP_DOCS.REPO_DEFAULT_BRANCH", "main")

        base_content = ""
        try:
            base_content = self.git_provider.get_pr_file_content(base_path, branch)
        except Exception as e:
            get_logger().warning(
                f"Failed to load performance file {base_path}: {e}"
            )

        custom_path = None
        for arg in args or []:
            if arg and isinstance(arg, str) and arg.startswith("--custom-context="):
                custom_path = arg.split("=", 1)[1].strip().strip('"').strip("'")
                break

        custom_content = ""
        if custom_path:
            try:
                custom_content = self.git_provider.get_pr_file_content(custom_path, branch)
            except Exception as e:
                get_logger().warning(
                    f"Failed to load custom performance file {custom_path}: {e}"
                )

        extra = get_settings().get("pr_performance", {}).get("extra_instructions", "") or ""
        if base_content:
            extra += (
                f"\n\nProject performance context from {base_path}:\n"
                f"{base_content}\n"
            )
        if custom_content:
            extra += (
                f"\n\nAdditional performance context from {custom_path}:\n"
                f"{custom_content}\n"
            )
        self.vars = {
            "title": self.git_provider.pr.title,
            "branch": self.git_provider.get_pr_branch(),
            "description": self.git_provider.get_pr_description(),
            "language": self.main_language,
            "diff": "",  # empty diff for initial calculation
            "extra_instructions": extra,
        }
        self.token_handler = TokenHandler(self.git_provider.pr, self.vars)

    async def run(self):
        try:
            if not self.git_provider.get_files():
                get_logger().info(f"PR has no files: {getattr(self.git_provider, 'pr_url', None)}, skipping performance check")
                return None

            get_logger().info(f'Checking PR performance: {getattr(self.git_provider, "pr_url", None)} ...')
            relevant_configs = {'pr_performance': dict(get_settings().get('pr_performance', {})),
                                'config': dict(get_settings().config)}
            get_logger().debug("Relevant configs", artifacts=relevant_configs)

            if get_settings().config.publish_output and not get_settings().config.get('is_auto_command', False):
                self.git_provider.publish_comment("Preparing performance check...", is_temporary=True)

            await retry_with_fallback_models(self._prepare_prediction)
            if not self.prediction:
                self.git_provider.remove_initial_comment()
                return None

            pr_performance_report = self._prepare_performance_report()
            get_logger().debug(f"PR performance output", artifact=pr_performance_report)

            should_publish = get_settings().config.publish_output
            if should_publish:
                self.git_provider.publish_comment(pr_performance_report)
            self.git_provider.remove_initial_comment()
        except Exception as e:
            get_logger().error(f"Failed to check PR performance: {e}")

    async def _prepare_prediction(self, model: str = None) -> None:
        self.patches_diff = get_pr_diff(self.git_provider,
                                        self.token_handler,
                                        model or get_settings().config.model,
                                        add_line_numbers_to_hunks=True,
                                        disable_extra_lines=False,)
        if self.patches_diff:
            get_logger().debug(f"PR diff", diff=self.patches_diff)
            self.prediction = await self._get_prediction(model or get_settings().config.model)
        else:
            get_logger().warning(f"Empty diff for PR: {getattr(self.git_provider, 'pr_url', None)}")
            self.prediction = None

    async def _get_prediction(self, model: str) -> str:
        variables = copy.deepcopy(self.vars)
        variables["diff"] = self.patches_diff
        from jinja2 import Environment, StrictUndefined
        environment = Environment(undefined=StrictUndefined)
        system_prompt = environment.from_string(get_settings().get('pr_performance_prompt', {}).get('system', "")) .render(variables)
        user_prompt = environment.from_string(get_settings().get('pr_performance_prompt', {}).get('user', "")) .render(variables)
        response, finish_reason = await self.ai_handler.chat_completion(
            model=model,
            system=system_prompt,
            user=user_prompt
        )
        return response

    def _prepare_performance_report(self) -> str:
        # This function can be customized to format the performance results
        return self.prediction or "No performance issues detected."
