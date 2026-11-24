<script setup lang="ts">
/**
 * /gasmix — справочник газовых реакций (Atmospherics) для SS14 (DeepLagoon).
 * Показывает требования, стехиометрию (вход/выход в молях и процентах) и условия.
 *
 * Данные: app/data/gas.json (газы + реакции), собирается scripts/build-gas-data.py
 * из прототипов Resources/. Страница только читает данные и группирует их.
 *
 * Два независимых сценария выбора:
 *  - выбран газ → показываем реакции, где он реагент или продукт;
 *  - выбрана реакция → показываем её стехиометрию, пороги и эффекты.
 * Одновременно активен только один из них (см. selectGas/selectReaction).
 */
import gasData from '~/data/gas.json'

/** Справочник газов: id, англ./рус. названия и цвет для точки-индикатора. */
type GasInfo = {
  id: string
  name: string
  nameRu: string
  color: string | null
}

/** Дополнительный вариант выхода (реакция может давать разный продукт при разных условиях). */
type GasOutputVariant = {
  label: string
  output: Record<string, number>
}

/** Одна газовая реакция. Суммы даны в молях; reactants — порог запуска в смеси. */
type GasReaction = {
  id: string
  title: string
  summary: string
  priority: number
  minTemp: number | null
  maxTemp: number | null
  tempFromCode: boolean
  minEnergy: number
  reactants: Record<string, number>
  input: Record<string, number>
  output: Record<string, number>
  outputVariants: GasOutputVariant[]
  notes: string[]
  effects: string[]
  source: string
}

type GasPayload = {
  gases: GasInfo[]
  reactions: GasReaction[]
}

const payload = gasData as GasPayload
const gases = payload.gases
const reactions = payload.reactions

const gasById = new Map(gases.map((g) => [g.id, g]))

/* ------------------------------- Состояние ------------------------------- */
// Пустая строка = «ничего не выбрано»; состояния газа и реакции взаимоисключающие.
const query = ref('')
const selectedGasId = ref<string>('')
const selectedReactionId = ref<string>('')

/* --------------------------- Названия и формат --------------------------- */

/** RU/EN названия газа с фолбэком на id, если газа нет в справочнике. */
function gasNames(id: string): { ru: string; en: string } {
  const gas = gasById.get(id)
  if (gas) return { ru: gas.nameRu, en: gas.name }
  return { ru: id, en: id }
}

function gasDisplayName(id: string): string {
  return gasNames(id).ru
}

/** Цвет точки-индикатора газа; null → в шаблоне рисуется пунктирный кружок. */
function gasColor(id: string): string | null {
  return gasById.get(id)?.color ?? null
}

/** Температура: до 2 знаков, лишние нули убираем, null → прочерк. */
function fmtTemp(v: number | null): string {
  if (v === null || v === undefined) return '—'
  return `${Number(v).toFixed(2).replace(/\.00$/, '').replace(/(\.\d)0$/, '$1')} K`
}

/** Моли: компактный вывод — крупные до 1 знака, мелкие до 3 без хвостовых нулей. */
function fmtMol(v: number): string {
  if (!Number.isFinite(v)) return '—'
  if (v === 0) return '0'
  if (Math.abs(v) >= 10) return v.toFixed(1).replace(/\.0$/, '')
  return Number(v.toFixed(3)).toString()
}

/** Сумма всех газов в смеси — база для процентов. */
function totalMoles(mix: Record<string, number>): number {
  return Object.values(mix).reduce((sum, v) => sum + v, 0)
}

/** Доля компонента в смеси в процентах (с разной точностью для больших/малых долей). */
function share(part: number, total: number): string {
  if (!total) return '—'
  const percent = (part / total) * 100
  const rounded = percent >= 10 ? Math.round(percent) : Math.round(percent * 10) / 10
  return `${rounded}%`
}

/** Человекочитаемое температурное условие реакции. */
function tempCondition(r: GasReaction): string {
  if (r.minTemp !== null && r.maxTemp !== null) return `${fmtTemp(r.minTemp)} … ${fmtTemp(r.maxTemp)}`
  if (r.minTemp !== null) return `≥ ${fmtTemp(r.minTemp)}`
  if (r.maxTemp !== null) return `≤ ${fmtTemp(r.maxTemp)}`
  return 'любая'
}

/** Газ есть среди продуктов — в том числе в одном из вариантов выхода. */
function hasOutputGas(r: GasReaction, gasId: string): boolean {
  if (gasId in r.output) return true
  return r.outputVariants.some((v) => gasId in v.output)
}

/** Подпись источника реакции (группа из данных). */
function sourceLabel(src: string): string {
  if (src === 'atmospherics') return 'Atmospherics'
  if (src === 'funky') return 'Funkystation / tg'
  return src
}

/* -------------------------------- Расчёты -------------------------------- */

/** Поиск по реакциям: id, заголовок, описание, источник, заметки и газы входа/выхода. */
const filteredReactions = computed(() => {
  const q = query.value.trim().toLowerCase()
  if (!q) return reactions
  const matches = (value: string) => value.toLowerCase().includes(q)
  return reactions.filter((r) => {
    if (matches(r.id) || matches(r.title) || matches(r.summary) || matches(r.source)) return true
    if (r.notes.some(matches)) return true
    for (const gid of Object.keys(r.input)) {
      if (matches(gid) || matches(gasDisplayName(gid))) return true
    }
    for (const gid of Object.keys(r.output)) {
      if (matches(gid) || matches(gasDisplayName(gid))) return true
    }
    for (const variant of r.outputVariants) {
      for (const gid of Object.keys(variant.output)) {
        if (matches(gid) || matches(gasDisplayName(gid))) return true
      }
    }
    return false
  })
})

/** Группировка отфильтрованных реакций по источнику; Atmospherics всегда первой. */
const groupedAll = computed(() => {
  const map = new Map<string, GasReaction[]>()
  for (const r of filteredReactions.value) {
    const key = r.source || 'other'
    const list = map.get(key)
    if (list) list.push(r)
    else map.set(key, [r])
  }
  const order = ['atmospherics', ...[...map.keys()].filter((k) => k !== 'atmospherics').sort()]
  return order.filter((k) => map.has(k)).map((k) => ({ key: k, label: sourceLabel(k), items: map.get(k)! }))
})

/**
 * Реакции, где выбранный газ встречается как реагент и/или продукт.
 * Роли показываются бейджами; реакции без ролей отбрасываются.
 */
const reactionsForSelectedGas = computed(() => {
  if (!selectedGasId.value) return []
  const gasId = selectedGasId.value
  return reactions
    .map((r) => {
      const roles: string[] = []
      if (gasId in r.reactants || gasId in r.input) roles.push('реагент')
      if (hasOutputGas(r, gasId)) roles.push('продукт')
      return { reaction: r, roles }
    })
    .filter((entry) => entry.roles.length > 0)
})

/** Реакция по id для блока деталей (null, если ничего не выбрано). */
const selectedReaction = computed(() => {
  if (!selectedReactionId.value) return null
  return reactions.find((r) => r.id === selectedReactionId.value) ?? null
})

/* ------------------------- Взаимоисключающий выбор ------------------------ */
// Выбор газа и выбор реакции сбрасывают друг друга — экран показывает один сценарий.

function selectGas(id: string) {
  selectedGasId.value = id
  selectedReactionId.value = ''
}

function selectReaction(id: string) {
  selectedReactionId.value = id
  selectedGasId.value = ''
}

function clearSelection() {
  selectedGasId.value = ''
  selectedReactionId.value = ''
}
</script>

<template>
  <!-- Шапка со счётчиками из данных. -->
  <div class="space-y-5">
    <header class="flex flex-wrap items-center gap-x-3 gap-y-1 px-1">
      <h1 class="text-xl font-bold leading-tight">Газовые реакции</h1>
      <p class="text-xs opacity-60">
        Стехиометрия, пропорции и условия атмосферных реакций.
      </p>
      <p class="ml-auto text-[11px] tabular-nums opacity-50">
        {{ reactions.length }} реакций · {{ gases.length }} газов
      </p>
    </header>

    <div class="grid items-start gap-5">
      <section class="min-w-0 space-y-5">
        <!-- Карточка выбора газа/реакции и деталей по выбору. -->
        <div class="card bg-base-100 shadow-xl">
          <div class="card-body gap-5">
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 class="card-title">Выбор</h2>
                <p class="text-sm opacity-60">Выберите газ или реакцию, чтобы посмотреть детали, пропорции и «дерево» требований.</p>
              </div>
              <button v-if="selectedGasId || selectedReactionId" class="btn btn-ghost btn-sm" @click="clearSelection">
                Сбросить
              </button>
            </div>

            <div class="grid gap-4 sm:grid-cols-2">
              <label class="flex flex-col gap-1.5">
                <span class="text-xs font-medium uppercase tracking-wide opacity-60">Газ</span>
                <select
                  class="select w-full"
                  :value="selectedGasId"
                  @change="selectGas(($event.target as HTMLSelectElement).value)"
                >
                  <option value="">— не выбран —</option>
                  <option v-for="g in gases" :key="g.id" :value="g.id">
                    {{ gasNames(g.id).ru }} ({{ gasNames(g.id).en }})
                  </option>
                </select>
              </label>
              <label class="flex flex-col gap-1.5">
                <span class="text-xs font-medium uppercase tracking-wide opacity-60">Реакция</span>
                <select
                  class="select w-full"
                  :value="selectedReactionId"
                  @change="selectReaction(($event.target as HTMLSelectElement).value)"
                >
                  <option value="">— не выбрана —</option>
                  <option v-for="r in reactions" :key="r.id" :value="r.id">
                    {{ r.title }}
                  </option>
                </select>
              </label>
            </div>

            <!-- Детали по выбранному газу: список реакций с ним и роли (реагент/продукт). -->
            <div v-if="selectedGasId" class="rounded-box border border-base-300 p-4 space-y-3">
              <div class="flex items-center justify-between gap-2">
                <h3 class="text-sm font-semibold flex items-center gap-2">
                  <span
                    class="inline-block h-3 w-3 rounded-full border border-base-300"
                    :style="gasColor(selectedGasId) ? { backgroundColor: gasColor(selectedGasId)! } : { backgroundColor: '#888' }"
                  />
                  {{ gasNames(selectedGasId).ru }}
                  <span class="text-xs font-normal opacity-60">{{ gasNames(selectedGasId).en }}</span>
                  <span class="font-mono text-xs opacity-60">{{ selectedGasId }}</span>
                </h3>
              </div>

              <div>
                <p class="text-xs uppercase tracking-[0.12em] text-base-content/50 mb-2">Реакции с этим газом</p>
                <div v-if="reactionsForSelectedGas.length === 0" class="text-sm opacity-60">Нет реакций в базе данных.</div>
                <ul v-else class="space-y-2">
                  <li
                    v-for="entry in reactionsForSelectedGas"
                    :key="entry.reaction.id"
                    class="rounded border border-base-300 p-2"
                  >
                    <div class="flex items-center justify-between gap-2">
                      <button class="text-left font-medium underline decoration-dotted" @click="selectReaction(entry.reaction.id)">
                        {{ entry.reaction.title }}
                        <span class="font-mono text-[10px] font-normal opacity-50">{{ entry.reaction.id }}</span>
                      </button>
                      <div class="flex shrink-0 gap-1">
                        <span
                          v-for="role in entry.roles"
                          :key="role"
                          class="badge badge-xs"
                          :class="role === 'продукт' ? 'badge-success badge-soft' : 'badge-ghost'"
                        >
                          {{ role }}
                        </span>
                      </div>
                    </div>
                    <p class="text-xs opacity-60 mt-1">
                      T: {{ tempCondition(entry.reaction) }} · {{ sourceLabel(entry.reaction.source) }}
                    </p>
                    <div class="mt-2 text-xs">
                      <span class="opacity-60">Вход:</span>
                      <span class="ml-1">
                        <span v-for="(amt, gid) in entry.reaction.input" :key="gid" class="inline-flex items-center gap-1 mr-2">
                          <span
                            class="inline-block h-2 w-2 rounded-full border border-base-300"
                            :style="gasColor(String(gid)) ? { backgroundColor: gasColor(String(gid))! } : { backgroundColor: '#888' }"
                          />
                          {{ gasNames(String(gid)).ru }}
                          <span class="font-mono opacity-70">{{ fmtMol(amt) }}</span>
                        </span>
                      </span>
                    </div>
                    <div class="mt-1 text-xs">
                      <span class="opacity-60">Выход:</span>
                      <span class="ml-1">
                        <span v-for="(amt, gid) in entry.reaction.output" :key="gid" class="inline-flex items-center gap-1 mr-2">
                          <span
                            class="inline-block h-2 w-2 rounded-full border border-base-300"
                            :style="gasColor(String(gid)) ? { backgroundColor: gasColor(String(gid))! } : { backgroundColor: '#888' }"
                          />
                          {{ gasNames(String(gid)).ru }}
                          <span class="font-mono opacity-70">{{ fmtMol(amt) }}</span>
                        </span>
                      </span>
                    </div>
                  </li>
                </ul>
              </div>
            </div>

            <!-- Детали по выбранной реакции: сводка, стехиометрия, пороги, заметки, эффекты. -->
            <div v-if="selectedReaction" class="rounded-box border border-base-300 p-4 space-y-4">
              <div class="flex items-start justify-between gap-2">
                <div>
                  <h3 class="text-sm font-semibold">{{ selectedReaction.title }}</h3>
                  <p class="font-mono text-[11px] opacity-50">{{ selectedReaction.id }}</p>
                </div>
              </div>

              <p v-if="selectedReaction.summary" class="text-sm opacity-75">{{ selectedReaction.summary }}</p>

              <div class="flex flex-wrap gap-1.5 text-xs">
                <span class="badge badge-outline badge-sm">приоритет {{ selectedReaction.priority }}</span>
                <span class="badge badge-outline badge-sm">T: {{ tempCondition(selectedReaction) }}</span>
                <span v-if="selectedReaction.tempFromCode" class="badge badge-ghost badge-sm" title="Ограничение по температуре задано в коде эффекта, а не в YAML">
                  лимит из кода
                </span>
                <span class="badge badge-ghost badge-sm">{{ sourceLabel(selectedReaction.source) }}</span>
                <span v-if="selectedReaction.minEnergy > 0" class="badge badge-ghost badge-sm">
                  энергия ≥ {{ fmtMol(selectedReaction.minEnergy) }}
                </span>
              </div>

              <!-- Стехиометрия: вход и выход в молях, с долей каждого газа в смеси. -->
              <div class="rounded-box bg-base-200/50 p-3 space-y-3">
                <div>
                  <p class="mb-1.5 text-xs uppercase tracking-[0.12em] text-base-content/50">
                    Вход · моль (доля в смеси)
                  </p>
                  <ul class="flex flex-wrap gap-2">
                    <li
                      v-for="(amt, gid) in selectedReaction.input"
                      :key="gid"
                      class="inline-flex items-center gap-2 rounded-full border border-base-300 bg-base-100 px-2.5 py-1 text-sm"
                    >
                      <span
                        class="inline-block h-3 w-3 shrink-0 rounded-full border border-base-300"
                        :style="gasColor(String(gid)) ? { backgroundColor: gasColor(String(gid))! } : { backgroundColor: '#888' }"
                      />
                      <span>{{ gasNames(String(gid)).ru }} <span class="text-[11px] opacity-60">{{ gasNames(String(gid)).en }}</span></span>
                      <span class="font-mono text-xs text-base-content/70">{{ fmtMol(amt) }}</span>
                      <span class="badge badge-ghost badge-xs tabular-nums">
                        {{ share(amt, totalMoles(selectedReaction.input)) }}
                      </span>
                    </li>
                  </ul>
                  <p v-if="Object.keys(selectedReaction.input).length === 0" class="text-sm opacity-50">—</p>
                </div>

                <div class="flex items-center gap-2 text-xs opacity-50">
                  <span class="text-base">↓</span>
                  <span>реакция</span>
                </div>

                <div>
                  <p class="mb-1.5 text-xs uppercase tracking-[0.12em] text-base-content/50">
                    Выход · моль (доля в продуктах)
                  </p>
                  <ul class="flex flex-wrap gap-2">
                    <li
                      v-for="(amt, gid) in selectedReaction.output"
                      :key="gid"
                      class="inline-flex items-center gap-2 rounded-full border border-success/40 bg-success/10 px-2.5 py-1 text-sm"
                    >
                      <span
                        class="inline-block h-3 w-3 shrink-0 rounded-full border border-base-300"
                        :style="gasColor(String(gid)) ? { backgroundColor: gasColor(String(gid))! } : { backgroundColor: '#888' }"
                      />
                      <span>{{ gasNames(String(gid)).ru }} <span class="text-[11px] opacity-60">{{ gasNames(String(gid)).en }}</span></span>
                      <span class="font-mono text-xs text-base-content/70">{{ fmtMol(amt) }}</span>
                      <span class="badge badge-ghost badge-xs tabular-nums">
                        {{ share(amt, totalMoles(selectedReaction.output)) }}
                      </span>
                    </li>
                  </ul>
                  <p v-if="Object.keys(selectedReaction.output).length === 0" class="text-sm opacity-50">—</p>
                </div>

                <div v-if="selectedReaction.outputVariants.length > 0" class="space-y-2">
                  <p class="text-xs uppercase tracking-[0.12em] text-base-content/50">Варианты выхода</p>
                  <div
                    v-for="variant in selectedReaction.outputVariants"
                    :key="variant.label"
                    class="flex flex-wrap items-center gap-2 text-xs"
                  >
                    <span class="badge badge-outline badge-xs">{{ variant.label }}</span>
                    <span
                      v-for="(amt, gid) in variant.output"
                      :key="gid"
                      class="inline-flex items-center gap-1 rounded-full border border-base-300 bg-base-100 px-2 py-0.5"
                    >
                      <span
                        class="inline-block h-2.5 w-2.5 shrink-0 rounded-full border border-base-300"
                        :style="gasColor(String(gid)) ? { backgroundColor: gasColor(String(gid))! } : { backgroundColor: '#888' }"
                      />
                      {{ gasNames(String(gid)).ru }}
                      <span class="font-mono opacity-60">{{ fmtMol(amt) }}</span>
                      <span class="tabular-nums opacity-60">{{ share(amt, totalMoles(variant.output)) }}</span>
                    </span>
                  </div>
                </div>
              </div>

              <div v-if="Object.keys(selectedReaction.reactants).length > 0">
                <p class="mb-1 text-xs uppercase tracking-[0.12em] text-base-content/50">Порог запуска (мин. молей в смеси)</p>
                <ul class="flex flex-wrap gap-2">
                  <li
                    v-for="(amt, gid) in selectedReaction.reactants"
                    :key="gid"
                    class="inline-flex items-center gap-1.5 rounded-full border border-dashed border-base-300 px-2 py-0.5 text-xs"
                  >
                    <span
                      class="inline-block h-2.5 w-2.5 shrink-0 rounded-full border border-base-300"
                      :style="gasColor(String(gid)) ? { backgroundColor: gasColor(String(gid))! } : { backgroundColor: '#888' }"
                    />
                    {{ gasNames(String(gid)).ru }}
                    <span class="font-mono opacity-70">{{ fmtMol(amt) }}</span>
                  </li>
                </ul>
              </div>

              <div v-if="selectedReaction.notes.length > 0">
                <p class="mb-1 text-xs uppercase tracking-[0.12em] text-base-content/50">Как работает</p>
                <ul class="list-disc space-y-1 pl-4 text-sm opacity-75">
                  <li v-for="note in selectedReaction.notes" :key="note">{{ note }}</li>
                </ul>
              </div>

              <div v-if="selectedReaction.effects.length > 0">
                <p class="mb-1 text-xs uppercase tracking-[0.12em] text-base-content/50">Эффекты (код)</p>
                <div class="flex flex-wrap gap-1">
                  <span v-for="ef in selectedReaction.effects" :key="ef" class="badge badge-ghost badge-sm font-mono">{{ ef }}</span>
                </div>
              </div>
            </div>

            <div v-if="!selectedGasId && !selectedReactionId" class="rounded-box border border-dashed border-base-300 px-4 py-10 text-center">
              <p class="text-sm opacity-60">Выберите газ или реакцию выше.</p>
            </div>
          </div>
        </div>
      </section>
    </div>

    <!-- Полный список реакций, сгруппированный по источнику, с поиском. -->
    <section class="space-y-3">
      <div class="flex items-center justify-between gap-2">
        <h2 class="text-lg font-semibold tracking-tight">Все реакции</h2>
        <div class="form-control w-full max-w-xs">
          <input
            v-model="query"
            type="text"
            class="input input-bordered input-sm w-full"
            placeholder="Поиск реакции или газа..."
          />
        </div>
      </div>
      <p class="text-sm text-base-content/60">
        Найдено: <span class="font-medium text-base-content">{{ filteredReactions.length }}</span> из {{ reactions.length }}
      </p>

      <section v-for="group in groupedAll" :key="group.key" class="flex flex-col gap-3">
        <h3 class="text-base font-semibold tracking-tight">{{ group.label }}</h3>
        <div class="grid gap-3 md:grid-cols-2">
          <article
            v-for="r in group.items"
            :key="r.id"
            class="card border border-base-300 bg-base-100 shadow-sm cursor-pointer transition-colors hover:border-base-content/30"
            @click="selectReaction(r.id)"
          >
            <div class="card-body gap-3 p-4">
              <div class="flex items-start justify-between gap-2">
                <div class="min-w-0">
                  <h4 class="text-base font-semibold leading-tight">{{ r.title }}</h4>
                  <p class="font-mono text-[11px] opacity-50">{{ r.id }}</p>
                </div>
                <span class="badge badge-outline badge-sm shrink-0">prio {{ r.priority }}</span>
              </div>

              <p v-if="r.summary" class="text-xs text-base-content/60 leading-snug">{{ r.summary }}</p>

              <div class="flex flex-wrap gap-1.5 text-xs">
                <span
                  class="badge badge-outline badge-sm"
                  :title="r.tempFromCode ? 'Лимит температуры задан в коде эффекта, а не в YAML' : undefined"
                >
                  T: {{ tempCondition(r) }}<template v-if="r.tempFromCode">*</template>
                </span>
                <span class="badge badge-ghost badge-sm">{{ sourceLabel(r.source) }}</span>
              </div>

              <div>
                <p class="mb-1 text-xs uppercase tracking-[0.12em] text-base-content/50">Вход · доля в смеси</p>
                <ul class="flex flex-wrap gap-2">
                  <li
                    v-for="(amt, gid) in r.input"
                    :key="gid"
                    class="inline-flex items-center gap-1.5 rounded-full border border-base-300 bg-base-200/40 px-2.5 py-1 text-sm"
                  >
                    <span
                      class="inline-block h-3 w-3 shrink-0 rounded-full border border-base-300"
                      :style="gasColor(String(gid)) ? { backgroundColor: gasColor(String(gid))! } : { backgroundColor: '#888' }"
                    />
                    <span>{{ gasNames(String(gid)).ru }}</span>
                    <span class="font-mono text-xs text-base-content/70">{{ fmtMol(amt) }}</span>
                    <span class="text-[11px] tabular-nums opacity-60">{{ share(amt, totalMoles(r.input)) }}</span>
                  </li>
                </ul>
                <p v-if="Object.keys(r.input).length === 0" class="text-sm text-base-content/50">—</p>
              </div>

              <div>
                <p class="mb-1 text-xs uppercase tracking-[0.12em] text-base-content/50">Выход</p>
                <ul class="flex flex-wrap gap-2">
                  <li
                    v-for="(amt, gid) in r.output"
                    :key="gid"
                    class="inline-flex items-center gap-1.5 rounded-full border border-success/40 bg-success/10 px-2.5 py-1 text-sm"
                  >
                    <span
                      class="inline-block h-3 w-3 shrink-0 rounded-full border border-base-300"
                      :style="gasColor(String(gid)) ? { backgroundColor: gasColor(String(gid))! } : { backgroundColor: '#888' }"
                    />
                    <span>{{ gasNames(String(gid)).ru }}</span>
                    <span class="font-mono text-xs text-base-content/70">{{ fmtMol(amt) }}</span>
                    <span class="text-[11px] tabular-nums opacity-60">{{ share(amt, totalMoles(r.output)) }}</span>
                  </li>
                </ul>
                <p v-if="Object.keys(r.output).length === 0" class="text-sm text-base-content/50">—</p>
                <p v-if="r.outputVariants.length > 0" class="mt-1 text-[11px] opacity-50">
                  Выход зависит от условий: {{ r.outputVariants.map((v) => v.label).join(' · ') }}
                </p>
              </div>
            </div>
          </article>
        </div>
      </section>

      <section v-if="filteredReactions.length === 0" class="card border border-dashed border-base-300 bg-base-100">
        <div class="card-body text-sm text-base-content/60">
          Ничего не найдено. Попробуй изменить запрос.
        </div>
      </section>
    </section>
  </div>
</template>
