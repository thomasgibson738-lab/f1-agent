# Working rules

How I'd like you to work with me on this project.

## Before acting
- Ask before installing new dependencies — don't add packages silently
- For multi-step tasks, show me the plan first, then execute step by step
- Surface architecture tradeoffs before deciding (e.g. "we could use X or Y, here's why I'd pick X")
- If a task is ambiguous, ask one clarifying question rather than guessing

## While coding
- Run code before claiming it works — don't say "this should work" without testing
- Show me the diff before deleting or rewriting more than ~50 lines of existing code
- Prefer small, focused commits over big sweeping changes
- When debugging, explain what you think is wrong before changing things

## Secrets and safety
- NEVER print, log, echo, or paste the value of ANTHROPIC_API_KEY or anything else from .env
- NEVER add .env to git, even if I ask — confirm I really mean it first
- If you spot something that looks like a credential in a file that isn't .env, flag it before continuing

## Communication style
- Concise over verbose — I'd rather have one clear paragraph than three padded ones
- When you finish a step, say what changed and what's next, not a full recap
- If I push back on something, engage with the substance rather than just agreeing

## When stuck
- If you've tried the same fix twice and it still fails, stop and tell me — don't keep iterating
- Suggest dropping back to a simpler approach if the current one is getting tangled
- Be honest about uncertainty: "I'm not sure this will work, but..." beats false confidence