# Reddit Post (r/programming, r/devtools, r/SideProject)

## Title
I built an autonomous documentation maintenance tool that watches your GitHub repos and opens PRs when docs go stale

## Body
Hey r/programming,

I built Tome ([tomehq.net](https://tomehq.net)) to solve a problem every team has: documentation that falls behind the code.

**The problem:** A developer ships a feature. The docs don't get updated. Weeks later, the docs are wrong and nobody knows when they went stale.

**What Tome does:**
- Hooks into your GitHub repo via webhook
- Watches every push to your default branch
- Uses LLM-powered diff analysis to identify code changes that need documentation
- Detects gaps between your code and existing docs
- Opens a PR with documentation updates that match your existing style

**What it's NOT:**
- Not a chatbot that answers questions about your docs (Chatbase, DocsBot, etc do that)
- Not a one-time doc generator
- It's an ongoing maintenance tool — a docs engineer that never sleeps

**"Why not just write a script that does this?"**

You could. The webhook + LLM call is the easy part. The hard part is:
- Style matching across existing docs
- Handling multi-file changes that span docs
- Scaling across repos and contributors
- Not generating garbage PRs your team ignores
- Keeping it running and maintained while you ship product

That's what you're paying $9/mo to not think about.

**Pricing:** $9/mo starter, $29/mo for auto-PR generation, $99/mo enterprise. 14-day free trial on all plans.

Would genuinely love feedback. Is this something your team would use? What would make it more useful?
