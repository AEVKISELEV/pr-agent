## Overview

The `/check_security` tool analyzes the pull request diff to highlight potential security issues.
Invoke it manually by commenting on a PR:

```
/check_security
```

It produces a bullet list of vulnerabilities and mitigation suggestions in the PR discussion.

## Configuration options

This command currently has no specific configuration options. You can provide a custom prompt by adding a file named `.ai/pr-agent/prompt/SECURITY.md` to the repository.
