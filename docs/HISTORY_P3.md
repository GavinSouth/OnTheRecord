# History — Phase 3 (context log)

Chronological log of every prompt/work item: what was asked, what was done, decisions, and what's next.
ROADMAP.md tracks feature completion; this file is the context a new session needs to pick up where we left off.

---

## 2026-10-23

### F3.1 — iOS project (started: design canvas)
- Asked: "resume where we left off" → F3.1 (F2.6 host steps stay deferred). New screens, so design canvas first (CLAUDE.md Design rule).
- Done: canvas [OnTheRecord iOS — App Shell](https://claude.ai/artifact/CDNJadM5PEhXNG665ENZLX), built from the OnTheRecord design system (tokens installed on the canvas). Six clickable 390×844 artboards: Sign in, Today (tab 1: combined 21-week heatmap card + habit rows with check/open/skip states), Todos (tab 2: due soon, lists/folders, Completed history entry), Notes (tab 3: search field filtering recent notes), Account sheet (name, time zone, Apple ID, dev-only server row, Sign out), Today in dark. Demo data only.
- Shell proposal: `TabView` with three tabs (Today / Todos / Notes), large titles, a toolbar action per tab (Account, New list, New note), account as a sheet from Today. Sign out is not styled `danger` (it destroys nothing).
- Design-system gaps found: a soft warning fill for the "Today" due pill (`#f7ecdc` used ad hoc → candidate `warning-soft` token); the tab bar and the section header style aren't components yet. Update the design system once the canvas is approved.
- Blocker for the build: Xcode isn't installed (only Command Line Tools). Needs Xcode from the App Store, then `sudo xcode-select -s /Applications/Xcode.app`.
- Next: user reviews the canvas → adjust → design-system update → Xcode project, OpenAPI client, Sign in with Apple, shell.

### F3.1 — canvas review, design-system update
- User: design decisions (tabs vs settings tab, heatmap placement, sign-out style) to be judged on the working prototype, not the canvas → canvas accepted as the build spec.
- Done: design system gains `warning-soft` (light `#faf0e2`, dark `#33260f`; `warning` on it 4.6:1 / 7.3:1. The first pick `#f7ecdc` was 4.45:1 and failed). README colour table + TodoRow "Due pill" guidance updated; canvas's token copy refreshed and the Todos pill uses it.
- Explained: Xcode is needed as the toolchain (iOS SDK, simulator, signing), not as the editor. Claude Code keeps working from the terminal (`xcodebuild`, `xcrun simctl`); the user opens Xcode only for one-time GUI steps (Apple ID/team, capabilities) or to run on the phone.
