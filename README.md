# Nuxt Minimal Starter

Look at the [Nuxt documentation](https://nuxt.com/docs/getting-started/introduction) to learn more.

## Setup

Make sure to install dependencies:

```bash
# npm
npm install

# pnpm
pnpm install

# yarn
yarn install

# bun
bun install
```

## Подготовка данных

Проект использует игровые данные SS14 (прототипы, карты, локализация). Перед генерацией данных скопируйте каталог `Resources` из билда станции/игры в корень репозитория:

```text
DeepLagoon-Utils/
├── Resources/          # из билда станции
│   ├── Prototypes/
│   ├── Locale/
│   ├── Maps/
│   └── ...
├── scripts/
└── ...
```

Затем сгенерируйте JSON-данные, которые использует сайт:

```bash
# все данные сразу
bash scripts/build-all.sh

# или по отдельности
python3 scripts/build-chem-data.py   # app/data/chem.json для /chem
python3 scripts/build-vendo-data.py  # app/data/vendo.json для /vendo
```

> Для скриптов нужен Python 3 с пакетом `PyYAML`.

## Development Server

Start the development server on `http://localhost:3000`:

```bash
# npm
npm run dev

# pnpm
pnpm dev

# yarn
yarn dev

# bun
bun run dev
```

## Production

Build the application for production:

```bash
# npm
npm run build

# pnpm
pnpm build

# yarn
yarn build

# bun
bun run build
```

Locally preview production build:

```bash
# npm
npm run preview

# pnpm
pnpm preview

# yarn
yarn preview

# bun
bun run preview
```

Check out the [deployment documentation](https://nuxt.com/docs/getting-started/deployment) for more information.
