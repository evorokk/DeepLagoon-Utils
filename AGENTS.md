# AGENTS.md

## Project
- DeepGoon wiki (SS14 DeepLagoon) — Nuxt 4 + Vue 3 site.
- Package manager: Bun (`bun.lock` committed). Use `bun install` / `bun run <script>`.

## Commands
- `bun install` — install deps (runs `postinstall` → `nuxt prepare`).
- `bun run dev` — dev server (Nuxt default: `http://localhost:3000`).
- `bun run build` — production build.
- `bun run generate` — static generation.
- `bun run preview` — preview production build.
- `bun run postinstall` (or `nuxt prepare`) — regenerate `.nuxt/` tsconfigs/types; required after a clean install or when `.nuxt/` is missing (root `tsconfig.json` only references `.nuxt/tsconfig.*.json`).
- No lint/test/typecheck scripts or CI workflows are configured in this repo.

## Architecture & wiring
- Nuxt 4 source root is `app/` (not repo root): shell/layout in `app/app.vue`, routes in `app/pages/*.vue`, shared UI in `app/components/*.vue`, global CSS in `app/assets/app.css`.
- Add a page by creating `app/pages/<name>.vue`; top-level navigation is hardcoded in `app/components/TopBar.vue` — update its menu links when adding/removing primary pages.
- `server/` exists but currently has no routes/middleware; `public/` holds static assets (`favicon.ico`, `robots.txt`).

## Styling
- Tailwind CSS v4 via `@tailwindcss/vite` in `nuxt.config.ts` (no `tailwind.config.*`/PostCSS tailwind config). Global entry is `app/assets/app.css` with `@import "tailwindcss";` and `@plugin "daisyui";`.
- daisyUI v5 is the UI component layer (classes like `navbar`, `btn`, `card`, `menu`, `bg-base-*` used in existing views); keep new UI consistent with these primitives.
- `nuxt.config.ts` sets `css: ["~/assets/app.css"]` and `compatibilityDate: "2025-07-15"`.
