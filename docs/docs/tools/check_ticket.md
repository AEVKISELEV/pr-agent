## Overview

The `/check_ticket` tool analyses the latest commit message for a ticket ID in the form `module: 0224008: [BUGS]`.
If a ticket ID is found, it queries the configured bug tracker for that ticket and checks whether the commit modifies the lines mentioned in the ticket description.

If the relevant lines are changed, the tool comments that the ticket problem was resolved; otherwise it notes that the ticket was not addressed.

```toml
/check_ticket
```

Set the bug tracker URL via an environment variable, e.g. in your `.env` file:

```bash
BUGTRACKER_URL="https://my-bugtracker"
```
