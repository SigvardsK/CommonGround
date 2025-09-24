# Dark Mode & Theming Implementation (Frontend)

This document summarizes the work done to add a robust dark mode to the webview, how it’s wired into the stack, where the changes live, and how to run and deploy it.

## Overview
- Introduced app-wide theme management using `next-themes` with Tailwind CSS variables.
- Added a small theme toggle in the chat header (Light/Dark/System). The temporary sidebar toggle was removed to avoid overlap with the “New Project” button.
- Refactored UI components to use semantic design tokens (bg-card, bg-background, text-foreground, text-muted-foreground, border, ring) instead of hardcoded light-only colors.
- Verified behavior with a visual QA pass and provided a checklist below.

## Key Changes
- Theming provider
  - Added `ThemeProvider` using `next-themes`.
  - File: `frontend/components/providers/ThemeProvider.tsx`.
  - Wrapped in `app/layout.tsx` and added `suppressHydrationWarning` to `<html>`.
- Theme toggle
  - Compact toggle in chat header.
  - File: `frontend/components/ui/theme-toggle.tsx`.
  - Used in `frontend/app/chat/components/ChatLayout.tsx`.
  - Note: The initial sidebar header toggle was removed (now only the header toggle remains).
- Tailwind + CSS variables
  - Tokens from `frontend/app/globals.css` (`--background`, `--foreground`, `--card`, `--sidebar-*`) are used via Tailwind theme mapping in `frontend/tailwind.config.ts`.
  - Components refactored to tokens so dark mode is automatic once the `dark` class is set on `<html>`.

## Files Touched (high‑impact)
- Providers & layout
  - `frontend/components/providers/ThemeProvider.tsx` (new)
  - `frontend/app/layout.tsx` (wrap with ThemeProvider)
- Toggle
  - `frontend/components/ui/theme-toggle.tsx` (new)
  - `frontend/app/chat/components/ChatLayout.tsx` (toggle placement, header tokens)
- Core views
  - `frontend/app/chat/components/ChatInput.tsx`
  - `frontend/app/chat/components/Workspace.tsx`
  - `frontend/app/chat/components/OutputPanel.tsx`
  - `frontend/app/chat/components/FlowView.tsx`
  - `frontend/app/chat/components/TimelineView.tsx`
  - `frontend/app/chat/components/KanbanView.tsx`
  - `frontend/app/chat/components/details/TurnBubble.tsx` (added `dark:prose-invert`)
  - `frontend/app/chat/components/details/ConversationDetailView.tsx`
  - `frontend/app/chat/components/details/NodeDetailPanel.tsx`
- Pages & misc
  - `frontend/app/chat/components/ProjectPage.tsx`
  - `frontend/app/chat/components/WelcomeScreen.tsx`
  - `frontend/app/my-agent/page.tsx`
  - `frontend/components/preview/OpenGraphCard.tsx`
  - `frontend/components/layout/LoadingSpinner.tsx`
  - `frontend/components/layout/AppSidebar.tsx` (refactor tokens, remove sidebar toggle)
  - `frontend/app/chat/components/PlanningPanel.tsx` (tokenize styles)

## Visual QA Checklist
- Global shell & headers
  - Backgrounds use `bg-background` or `bg-card`; borders visible in both themes.
  - No initial flash; theme persistence works across reloads.
- Inputs & focus
  - Inputs/textarea focus use `ring-ring`, not fixed black borders.
  - Placeholders & muted text: `text-muted-foreground`.
- Chat & markdown
  - User bubble `bg-muted`, assistant bubble `bg-card`.
  - Markdown uses `prose` with `dark:prose-invert`.
  - Tool parameter blocks use `bg-muted` and readable text.
- Workspace views
  - Tabs highlight with `bg-muted`.
  - Timeline rails use `bg-muted`; status blocks readable.
  - Kanban cards use `bg-card`; descriptions `text-muted-foreground`.
- Sidebar
  - Project list hover/selection use `bg-accent`.
  - Settings dialog: left panel `bg-card`, active tab `bg-accent`.
- Loading & dialogs
  - Spinner uses `border-muted-foreground`.
  - Dialogs/Screens use `bg-card`, backdrops remain `bg-black/80` (OK for both themes).

## How To Run (No Yarn)
- Local development (hot reloading):
  - `cd frontend`
  - `cp env.example .env.local`
    - `NEXT_PUBLIC_API_URL=http://localhost:8000`
    - `NEXT_PUBLIC_WS_URL=ws://localhost:8000`
  - `npm ci` (or `npm install`)
  - `npm run dev`
  - Visit: `http://localhost:3000/webview`

- Production build (static export):
  - `cd frontend`
  - `npm ci` && `npm run build` (outputs to `frontend/out`)
  - In Docker, this `out/` is copied into the core image automatically (see Dockerfile).

## Docker: Update Running Deployment
- From `deployment/`:
  - Rebuild only core (contains backend + static webview):
    - `docker compose build core`
    - `docker compose up -d core`
  - Or rebuild all:
    - `docker compose up -d --build`
- No need to manually delete the container; Compose recreates it.
- If UI looks cached, try:
  - `docker compose build --no-cache core`
  - `docker compose up -d core`
  - Hard-refresh browser.

## Notes & Warnings
- ESLint in CI/build: Unused variables fail builds. We fixed the `theme` var in `ThemeToggle` to keep builds green.
- Next.js warning: "redirects will not automatically work with output: export" is expected with static export + custom redirects. Our use is acceptable; the app path is under `/webview`.
- Bridge logs: During Docker builds, you may see `fatal: not a git repository` from the bridge build. It’s a benign message; the build continues.

## Future Work
- Optional: Add theme toggle to Settings dialog (“Appearance: Light/Dark/System”).
- Optional: Replace ad-hoc drag-over styling with ring-based outline for higher contrast in dark mode.
- Optional: Centralize primary/brand color usage in tokens if you want tighter control over link/chip colors across themes.

