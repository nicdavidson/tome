# Show HN: Tome – Autonomous documentation maintenance that opens PRs

**URL:** https://tomehq.net

Tome watches your GitHub repos for code changes and automatically opens pull requests to keep your documentation current.

It's not a docs chatbot (there are plenty of those). It's a docs *writer*.

**How it works:**
1. Connect your repo via GitHub webhook
2. Push code as usual
3. Tome analyzes diffs, detects documentation gaps, and opens PRs with updates that match your existing style

**What makes it different from Chatbase/DocsBot/etc:**
- Those tools help users *search* existing docs
- Tome *writes and maintains* docs
- It opens PRs you can review, not just generate text

**"Why not just build this yourself?"**

You could wire up a webhook and an LLM call in a day. The hard part is everything else: matching your doc style, handling multi-file changes, not generating garbage PRs your team learns to ignore, scaling across repos and contributors, and keeping it running while you ship product. That's the problem space Tome lives in.

**Pricing:** Starting at $9/mo with 14-day free trial. All plans include gap detection; Pro ($29/mo) adds automatic PR generation.

It dogfoods itself — PR #1 on its own repo was opened by Tome analyzing its own commit: https://github.com/nicdavidson/tome/pull/1

Would love feedback on the approach. Is automated doc maintenance something your team would use?
