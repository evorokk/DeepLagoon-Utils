# AGENTS.md

## Проект
- DeepLagoon-Utils (SS14 DeepLagoon): Nuxt 4 + Vue 3. Пакетный менеджер: Bun (`bun.lock`) — `bun install` / `bun run <script>`.

## Команды
- `bun install` (в т.ч. `postinstall` → `nuxt prepare`)
- `bun run dev` / `build` / `generate` / `preview`
- `nuxt prepare` при чистой установке/отсутствии `.nuxt` (корневой `tsconfig` ссылается на `.nuxt/tsconfig.*.json`)
- Линт/тест/typecheck/CI не настроены.

## Архитектура (Nuxt 4, root = `app/`)
- `app/app.vue` — оболочка/лейаут; маршруты: `app/pages/*.vue`; UI: `app/components/*.vue`; стили: `app/assets/app.css`.
- Новая страница: `app/pages/<name>.vue`. Меню навигации задаётся в `app/components/TopBar.vue` — при добавлении/удалении основных страниц обновлять ссылки.
- Данные/скрипты: `app/data/` (JSON для `/chem`, поиска и т.п.), вспомогательные скрипты в `scripts/` (пример: `scripts/build-chem-data.py`).
- `server/` пустой (без маршрутов/middleware); `public/` — статика сайта (`favicon.ico`, `robots.txt`).

## Стилизация
- Tailwind CSS v4 через `@tailwindcss/vite` в `nuxt.config.ts` (без `tailwind.config.*`, без отдельного PostCSS для Tailwind). Вход: `app/assets/app.css` (`@import "tailwindcss";`, `@plugin "daisyui";`).
- daisyUI v5: придерживаться существующих классов (`navbar`, `btn`, `card`, `menu`, `bg-base-*`).
- `nuxt.config.ts`: `css: ["~/assets/app.css"]`, `compatibilityDate: "2025-07-15"`.

## Дополнительно
- Назначение: вики и утилиты для SS14 (DeepLagoon). См. ссылку в README/описании при необходимости.
- Игровые данные: `Resources/` в корне (прототипы/карты/локализация/текстуры и т.д., в `.gitignore`). Источник данных для сайта (корабли/сущности/рецепты); не путать с `public/`.
- Страницы: `/` (`app/pages/index.vue`), `/vendo` (`app/pages/vendo.vue`) — выбор выгодного снятия оборудования с покупных шаттлов (стоимость, возврат, потери, кратные объекты), данные из `Resources/`; `/chem` (`app/pages/chem.vue`) — расчёт рецептов под колбу/количество + заметки (в разработке).
- Git: после изменений делать коммит.
