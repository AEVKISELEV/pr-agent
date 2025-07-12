## Overview

The `check_tests` tool analyzes the pull request changes and existing review notes to suggest test scenarios that should be added.

Invoke it manually by commenting on a PR:

```
/check_tests
```

The tool returns a list of recommended tests in the PR discussion.

## Configuration options

This command currently has no specific configuration options.

### Custom prompt

You can provide a custom prompt for this tool by adding a file named
`.ai/pr-agent/prompt/check-tests.md` to the repository being reviewed. When
present, its contents will replace the default prompt used to generate test
scenarios.
