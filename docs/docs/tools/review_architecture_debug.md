## Overview

The `review_architecture_debug` tool prepares the same prompt used by `/review_architecture`
but does not send it to an AI model. Instead, it returns the full system and user
prompts so you can inspect them.

Invoke the tool manually by commenting on a PR:

```
/review_architecture_debug
```

Optional parameters are identical to `/review_architecture`.
