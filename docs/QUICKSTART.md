# Orchestra Quickstart Guide

**For Developers and Creative Technologists**

Get Orchestra running in 2 minutes. No PhD required.

---

## What Is This?

Orchestra is a **cognitive co-pilot** for Claude Code. It watches how you're doing and adjusts Claude's behavior:

- **Frustrated?** → Claude backs off, validates your feelings first
- **In the zone?** → Claude stays quiet, minimal interruption
- **Overwhelmed?** → Claude breaks things down into smaller pieces
- **Exhausted?** → Claude suggests easy wins or taking a break

Think of it like having a TD who knows when to help and when to leave you alone.

---

## Install (30 seconds)

```bash
# Option 1: From PyPI
pip install cognitive-orchestra

# Option 2: From source
git clone https://github.com/JosephOIbrahim/Orchestra.git
cd Orchestra
pip install -e .
```

---

## Activate (30 seconds)

```bash
# Install the Claude Code hook
orchestra install-hook

# Restart Claude Code (important!)
# Close and reopen your terminal/IDE
```

That's it. Orchestra is now active.

---

## Verify It's Working

```bash
# Check status
orchestra status

# You should see something like:
# ┌─────────────────────────────────────────┐
# │ ORCHESTRA STATUS                        │
# │ State: focused | Energy: high           │
# │ Burnout: GREEN | Momentum: building     │
# └─────────────────────────────────────────┘
```

---

## Daily Usage

### You Don't Need To Do Anything

Orchestra runs automatically. It reads your messages, detects your state, and adjusts Claude's responses.

### If You Want To Check In

```bash
orchestra status          # See current state
orchestra status --short  # One-line version
```

### If You Need To Adjust

```bash
orchestra set -b YELLOW   # Mark yourself as getting tired
orchestra set -b ORANGE   # Mark yourself as burning out
orchestra set -e low      # Set energy to low
```

### If You Want The Dashboard

```bash
orchestra                 # Launches TUI dashboard
```

---

## What The Colors Mean

| Color | Meaning | What Claude Does |
|-------|---------|------------------|
| 🟢 GREEN | You're good | Normal operation |
| 🟡 YELLOW | Getting tired | "Quick break soon?" |
| 🟠 ORANGE | Burning out | "What's blocking you?" |
| 🔴 RED | Done for today | Full stop, recovery mode |

---

## The 7 Experts

Orchestra routes to different "experts" based on your signals:

| Expert | When It Activates | What It Does |
|--------|-------------------|--------------|
| **Validator** | You're frustrated, ALL CAPS | Empathy first, no fixing |
| **Scaffolder** | You're overwhelmed | Breaks things down |
| **Restorer** | You're exhausted | Easy wins, rest OK |
| **Refocuser** | You went on tangent | Gentle redirect |
| **Celebrator** | You finished something | Acknowledges the win |
| **Socratic** | You're exploring | Guides discovery |
| **Direct** | You're in flow | Stays out of the way |

---

## Troubleshooting

### "Orchestra not responding"

```bash
# Check if hook is installed
cat ~/.claude/hooks/hooks.json

# Should contain "orchestra.hooks"
# If not, reinstall:
orchestra install-hook
```

### "State seems wrong"

```bash
# Reset session
orchestra set -b GREEN -e high

# Or manually edit state
cat ~/.orchestra/state/cognitive_state.json
```

### "Want to disable temporarily"

```bash
orchestra uninstall-hook
# Restart Claude Code
```

---

## Philosophy

Orchestra is built for **neurodivergent brains**:

1. **Safety first** — Emotional safety before productivity
2. **Ship over perfect** — Working beats polished
3. **Protect momentum** — Don't break flow
4. **Write it down** — External memory over mental load
5. **Rest is productive** — Recovery without guilt

---

## Need Help?

- **Issues:** https://github.com/JosephOIbrahim/Orchestra/issues
- **README:** https://github.com/JosephOIbrahim/Orchestra

---

*Orchestra v5.0.0 — Built for humans who think differently*
