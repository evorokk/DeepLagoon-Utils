# DeepLagoon-Utils

Веб-инструменты и справочные материалы для [Space Station 14](https://spacestation14.com/) (сборка DeepLagoon). Сайт собирает игровые данные из прототипов и превращает их в удобные калькуляторы и таблицы.

## Что умеет

- **Химия** (`/chem`) — расчёт рецептов: партии, выход, шаг перелива, дерево подрецептов и заметки.
- **Газы** (`/gasmix`) — справочник атмосферных реакций: вход и выход в молях и процентах, условия запуска, эффекты.
- **Оборудование** (`/vendo`) — выбор выгодного снятия оборудования с покупных шаттлов: стоимость, возврат, потери, кратные объекты.

## Стек

- [Nuxt 4](https://nuxt.com/) + Vue 3, корень приложения — `app/`
- [Tailwind CSS v4](https://tailwindcss.com/) + [daisyUI v5](https://daisyui.com/)
- Пакетный менеджер — [Bun](https://bun.sh/) (`bun.lock`)
- Python 3 + `PyYAML` для сборки данных

## Установка и запуск

```bash
bun install        # также выполняет nuxt prepare
bun run dev        # http://localhost:3000
```

Сборка и локальный просмотр:

```bash
bun run build
bun run preview
```

Статическая генерация:

```bash
bun run generate
```

## Подготовка данных

Игровые данные в репозиторий не входят. Скопируйте каталог `Resources` из билда станции в корень проекта:

```text
DeepLagoon-Utils/
├── Resources/        # прототипы, карты, локализация, текстуры
│   ├── Prototypes/
│   ├── Locale/
│   ├── Maps/
│   └── ...
├── scripts/
└── ...
```

Затем сгенерируйте JSON, который использует сайт:

```bash
bash scripts/build-all.sh            # всё сразу
```

Или по отдельности:

```bash
python3 scripts/build-chem-data.py   # app/data/chem.json      → /chem
python3 scripts/build-gas-data.py    # app/data/gas.json       → /gasmix
python3 scripts/build-vendo-data.py  # app/data/vendo.json     → /vendo
```

Требования для скриптов: Python 3 и пакет `PyYAML`.

## Структура проекта

```text
app/
├── app.vue              # оболочка приложения
├── pages/               # маршруты: index, chem, gasmix, vendo
├── components/          # UI, включая TopBar с навигацией
├── data/                # сгенерированный JSON
└── assets/app.css       # Tailwind + daisyUI
scripts/                 # генераторы данных из Resources/
public/                  # статика (favicon, robots.txt)
```

Новая страница — файл `app/pages/<name>.vue`. Если она основная, добавьте ссылку в `app/components/TopBar.vue`.

## Лицензия

Материалы проекта предназначены для сообщества DeepLagoon. Игровые данные принадлежат их правообладателям (Space Station 14 / DeepLagoon).
