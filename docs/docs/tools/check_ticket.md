## Overview

The `/check_ticket` tool analyses the latest commit message for a ticket ID in the form `module: 0224008: [BUGS]`.
If a ticket ID is found, it queries the configured bug tracker for that ticket and then uses an AI model to decide whether the commit fixes the described problem. The ticket description and the commit diff are provided to the model, which returns a short verdict.

If the model determines that the issue is fixed, the tool comments that the ticket problem was resolved; otherwise it notes that the ticket was not addressed.

```toml
/check_ticket
```

Set the bug tracker URL via an environment variable, e.g. in your `.env` file:

```bash
BUGTRACKER_URL="https://my-bugtracker"
```
