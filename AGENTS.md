# AGENTS.md

## Проект
- Вики DeepGoon (SS14 DeepLagoon) — сайт на Nuxt 4 + Vue 3.
- Менеджер пакетов: Bun (`bun.lock` закоммичен). Используйте `bun install` / `bun run <script>`.

## Команды
- `bun install` — установка зависимостей (запускает `postinstall` → `nuxt prepare`).
- `bun run dev` — сервер разработки (по умолчанию Nuxt: `http://localhost:3000`).
- `bun run build` — production-сборка.
- `bun run generate` — статическая генерация.
- `bun run preview` — предпросмотр production-сборки.
- `bun run postinstall` (или `nuxt prepare`) — пересоздание tsconfig/типов в `.nuxt/`; требуется после чистой установки или если `.nuxt/` отсутствует (корневой `tsconfig.json` ссылается только на `.nuxt/tsconfig.*.json`).
- В этом репозитории не настроены скрипты lint/test/typecheck и CI-workflow.

## Архитектура и связи
- Корень исходников Nuxt 4 — `app/` (а не корень репозитория): оболочка/лейаут в `app/app.vue`, маршруты в `app/pages/*.vue`, общие UI-компоненты в `app/components/*.vue`, глобальные стили в `app/assets/app.css`.
- Чтобы добавить страницу, создайте `app/pages/<name>.vue`; верхняя навигация захардкожена в `app/components/TopBar.vue` — обновляйте ссылки меню при добавлении/удалении основных страниц.
- Директория `server/` существует, но сейчас не содержит маршрутов/middleware; `public/` хранит статические ассеты (`favicon.ico`, `robots.txt`).

## Стилизация
- Tailwind CSS v4 подключён через `@tailwindcss/vite` в `nuxt.config.ts` (нет `tailwind.config.*` и отдельной PostCSS-конфигурации Tailwind). Точка входа глобальных стилей — `app/assets/app.css` с `@import "tailwindcss";` и `@plugin "daisyui";`.
- daisyUI v5 — слой UI-компонентов (в существующих представлениях используются классы вроде `navbar`, `btn`, `card`, `menu`, `bg-base-*`); сохраняйте единообразие с этими примитивами при добавлении нового интерфейса.
- В `nuxt.config.ts` заданы `css: ["~/assets/app.css"]` и `compatibilityDate: "2025-07-15"`.
