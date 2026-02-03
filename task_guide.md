

## ✅ High-Accuracy Research Prompt for Scrapy

> You are acting as a senior Scrapy core contributor performing issue triage.
>
> Your task is to **actively browse the Scrapy GitHub repository issues AND related pull requests** and identify the **most technically complex, non-trivial open issues** that require deep architectural understanding to solve.
>
> ⚠️ You MUST read multiple issues and PR discussions before answering. Do NOT rely on prior knowledge.
>
> ---
>
> ### Only consider issues that involve at least one of the following:
>
> * Async / Await / Twisted reactor / asyncio integration
> * Pipelines, middlewares, downloader handlers, scheduler, or engine internals
> * Failing tests, flaky tests, CI instability, or regressions
> * Race conditions, concurrency bugs, lifecycle/state management problems
> * Incorrect request/response handling, retry logic, or HTTP status handling
> * File handling, streaming, encoding, or filesystem edge cases
> * Proxy, headers, timeout, or networking edge cases
>
> ---
>
> ### Strictly ignore:
>
> * Documentation, typing, comments, or refactor-only issues
> * “Good first issue”, “easy”, or beginner tags
> * UI, spelling, formatting, or trivial cleanups
>
> ---
>
> ### Extra filter (very important):
>
> Prefer issues whose likely fix would require **changes across 3 or more files**, such as:
>
> * pipeline + middleware + test
> * downloader + retry middleware + tests
> * engine/scheduler + pipeline + tests
> * core module + utils + tests
>
> These indicate deep cross-component bugs.
>
> ---
>
> ### For each issue you select, provide:
>
> 1. Issue title
> 2. Direct GitHub link
> 3. Why this issue is technically difficult
> 4. Which Scrapy internal components are involved
> 5. Why solving it likely requires modifying 3–4 files
> 6. What deep Scrapy/Twisted/async knowledge is required
> 7. summery of what you have resoleve
>
> ---
>
> ### Prioritize issues that:
>
> * Have been open for a long time with discussion but no solution
> * Mention failing tests but unclear root cause
> * Reference async behavior, pipelines, middleware, or scheduler
> * Have related PRs that were attempted but not merged
>
