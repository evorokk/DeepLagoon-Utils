<script setup lang="ts">
/**
 * /gasmix — справочник газовых реакций (Atmospherics) для SS14 (DeepLagoon).
 * Показывает требования, стехиометрию (вход/выход в молях и процентах) и условия.
 */
import gasData from '~/data/gas.json'

type GasInfo = {
  id: string
  name: string
  nameRu: string
  color: string | null
}

type GasOutputVariant = {
  label: string
  output: Record<string, number>
}

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

type SavedGasItem = {
  key: string
  kind: 'gas' | 'reaction'
  id: string
}

const payload = gasData as GasPayload
const gases = payload.gases
const reactions = payload.reactions

const gasById = new Map(gases.map((g) => [g.id, g]))
const reactionById = new Map(reactions.map((r) => [r.id, r]))

const query = ref('')
const selectedGasId = ref<string>('')
const selectedReactionId = ref<string>('')

const SAVED_STORAGE_KEY = 'gasmix:saved'
const savedItems = ref<SavedGasItem[]>([])
const savedOpen = ref<Set<string>>(new Set())

function gasNames(id: string): { ru: string; en: string } {
  const gas = gasById.get(id)
  if (gas) return { ru: gas.nameRu, en: gas.name }
  return { ru: id, en: id }
}

function gasDisplayName(id: string): string {
  return gasNames(id).ru
}

function gasColor(id: string): string | null {
  return gasById.get(id)?.color ?? null
}

function fmtTemp(v: number | null): string {
  if (v === null || v === undefined) return '—'
  return `${Number(v).toFixed(2).replace(/\.00$/, '').replace(/(\.\d)0$/, '$1')} K`
}

function fmtMol(v: number): string {
  if (!Number.isFinite(v)) return '—'
  if (v === 0) return '0'
  if (Math.abs(v) >= 10) return v.toFixed(1).replace(/\.0$/, '')
  return Number(v.toFixed(3)).toString()
}

function totalMoles(mix: Record<string, number>): number {
  return Object.values(mix).reduce((sum, v) => sum + v, 0)
}

function share(part: number, total: number): string {
  if (!total) return '—'
  const percent = (part / total) * 100
  const rounded = percent >= 10 ? Math.round(percent) : Math.round(percent * 10) / 10
  return `${rounded}%`
}

function tempCondition(r: GasReaction): string {
  if (r.minTemp !== null && r.maxTemp !== null) return `${fmtTemp(r.minTemp)} … ${fmtTemp(r.maxTemp)}`
  if (r.minTemp !== null) return `≥ ${fmtTemp(r.minTemp)}`
  if (r.maxTemp !== null) return `≤ ${fmtTemp(r.maxTemp)}`
  return 'любая'
}

function hasOutputGas(r: GasReaction, gasId: string): boolean {
  if (gasId in r.output) return true
  return r.outputVariants.some((v) => gasId in v.output)
}

function reactionTitle(id: string): string {
  return reactionById.get(id)?.title ?? id
}

function sourceLabel(src: string): string {
  if (src === 'atmospherics') return 'Atmospherics'
  if (src === 'funky') return 'Funkystation / tg'
  return src
}

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

// Reactions that involve selected gas (as reactant and/or product)
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

const selectedReaction = computed(() => {
  if (!selectedReactionId.value) return null
  return reactions.find((r) => r.id === selectedReactionId.value) ?? null
})

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

function isSaved(kind: 'gas' | 'reaction', id: string): boolean {
  return savedItems.value.some((s) => s.kind === kind && s.id === id)
}

function toggleSave(kind: 'gas' | 'reaction', id: string) {
  if (isSaved(kind, id)) {
    savedItems.value = savedItems.value.filter((s) => !(s.kind === kind && s.id === id))
  } else {
    savedItems.value = [
      ...savedItems.value,
      { key: `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`, kind, id },
    ]
  }
}

function removeSaved(key: string) {
  savedItems.value = savedItems.value.filter((s) => s.key !== key)
  const next = new Set(savedOpen.value)
  next.delete(key)
  savedOpen.value = next
}

function toggleSavedOpen(key: string) {
  const next = new Set(savedOpen.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  savedOpen.value = next
}

function loadSaved(item: SavedGasItem) {
  if (item.kind === 'gas') {
    selectedGasId.value = item.id
    selectedReactionId.value = ''
  } else {
    selectedReactionId.value = item.id
    selectedGasId.value = ''
  }
}

onMounted(() => {
  if (!import.meta.client) return
  try {
    const stored = localStorage.getItem(SAVED_STORAGE_KEY)
    if (!stored) return
    const parsed: unknown = JSON.parse(stored)
    if (!Array.isArray(parsed)) return
    savedItems.value = parsed.filter((item): item is SavedGasItem => {
      if (typeof item !== 'object' || item === null) return false
      const it = item as SavedGasItem
      return typeof it.key === 'string' && (it.kind === 'gas' || it.kind === 'reaction') && typeof it.id === 'string'
    })
  } catch {
    // ignore
  }
})

watch(savedItems, (value) => {
  if (!import.meta.client) return
  try {
    localStorage.setItem(SAVED_STORAGE_KEY, JSON.stringify(value))
  } catch {
    // ignore
  }
}, { deep: true })
</script>

<template>
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

    <div class="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_21rem]">
      <section class="min-w-0 space-y-5">
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

            <!-- Details for selected gas -->
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
                <button
                  class="btn btn-xs"
                  :class="isSaved('gas', selectedGasId) ? 'btn-ghost' : 'btn-primary btn-soft'"
                  @click="toggleSave('gas', selectedGasId)"
                >
                  {{ isSaved('gas', selectedGasId) ? 'Сохранено' : 'Сохранить' }}
                </button>
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

            <!-- Details for selected reaction -->
            <div v-if="selectedReaction" class="rounded-box border border-base-300 p-4 space-y-4">
              <div class="flex items-start justify-between gap-2">
                <div>
                  <h3 class="text-sm font-semibold">{{ selectedReaction.title }}</h3>
                  <p class="font-mono text-[11px] opacity-50">{{ selectedReaction.id }}</p>
                </div>
                <button
                  class="btn btn-xs shrink-0"
                  :class="isSaved('reaction', selectedReaction.id) ? 'btn-ghost' : 'btn-primary btn-soft'"
                  @click="toggleSave('reaction', selectedReaction.id)"
                >
                  {{ isSaved('reaction', selectedReaction.id) ? 'Сохранено' : 'Сохранить' }}
                </button>
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

              <!-- Stoichiometry: input / output with mole shares -->
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

      <!-- Saved aside -->
      <aside class="space-y-3 xl:sticky xl:top-4">
        <div class="card bg-base-100 shadow-xl">
          <div class="card-body gap-3">
            <div class="flex items-center justify-between gap-2">
              <h2 class="card-title text-base">Сохранённые</h2>
              <span class="badge badge-ghost badge-sm tabular-nums">{{ savedItems.length }}</span>
            </div>

            <div v-if="savedItems.length === 0" class="text-xs opacity-60">
              Сохраняйте газ или реакцию кнопкой «Сохранить».
            </div>

            <div v-else class="space-y-2">
              <div v-for="s in savedItems" :key="s.key" class="rounded-box border border-base-300 p-2">
                <div class="flex items-center gap-2">
                  <button
                    class="btn btn-ghost btn-xs btn-square"
                    @click="toggleSavedOpen(s.key)"
                    :aria-expanded="savedOpen.has(s.key)"
                  >
                    <svg viewBox="0 0 16 16" fill="none" class="size-3 transition-transform" :class="savedOpen.has(s.key) ? 'rotate-180' : ''">
                      <path d="M4 6.5L8 10.5L12 6.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" />
                    </svg>
                  </button>
                  <button class="min-w-0 flex-1 text-left text-sm font-medium truncate" @click="loadSaved(s)">
                    <span v-if="s.kind === 'gas'">{{ gasNames(s.id).ru }} <span class="text-[10px] opacity-60">{{ gasNames(s.id).en }}</span></span>
                    <span v-else>{{ reactionTitle(s.id) }}</span>
                  </button>
                  <button class="btn btn-ghost btn-xs btn-square" @click="removeSaved(s.key)" title="Удалить">
                    <svg viewBox="0 0 16 16" fill="none" class="size-3.5">
                      <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" />
                    </svg>
                  </button>
                </div>
                <div v-if="savedOpen.has(s.key)" class="mt-2 text-xs opacity-70 pl-8">
                  <span class="badge badge-ghost badge-xs">{{ s.kind === 'gas' ? 'Газ' : 'Реакция' }}</span>
                  <span class="ml-1 font-mono">{{ s.id }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </aside>
    </div>

    <!-- All reactions below -->
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
