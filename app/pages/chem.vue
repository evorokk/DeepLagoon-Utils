<script setup lang="ts">
import chem from '~/data/chem.json'

type Reagent = {
  id: string
  name: string
  color: string | null
}

type Reaction = {
  id: string
  group: string
  reactants: Record<string, number>
  products: Record<string, number>
  minTemp: number | null
  maxTemp: number | null
  mixer: string[]
}

type Note = {
  id: string
  text: string
  createdAt: string
}

type IngredientRow = {
  id: string
  name: string
  color: string | null
  perBatch: number
  total: number
  share: number
}

type RecipeCalc = {
  reaction: Reaction
  yieldPerBatch: number
  batches: number
  produced: number
  inputPerBatch: number
  productsPerBatch: number
  inputVolume: number
  productsVolume: number
  batchVolume: number
  totalVolume: number
  free: number
  fits: boolean
  runs: number
  ingredients: IngredientRow[]
}

const reagents = chem.reagents as Reagent[]
const reactions = chem.reactions as Reaction[]

const GROUP_LABELS: Record<string, string> = {
  chemicals: 'Химикаты',
  medicine: 'Медицина',
  drinks: 'Напитки',
  food: 'Еда',
  fun: 'Развлечения',
  cleaning: 'Чистящие средства',
  botany: 'Ботаника',
  biological: 'Биология',
  pyrotechnic: 'Пиротехника',
  gas: 'Газы',
  single_reagent: 'Из одного реагента',
}
const GROUP_ORDER = Object.keys(GROUP_LABELS)

const reagentById = new Map(reagents.map(reagent => [reagent.id, reagent]))
const producibleCount = new Set(reactions.flatMap(reaction => Object.keys(reaction.products))).size

const flaskVolume = ref<number | string>(100)
const targetVolume = ref<number | string>(30)
const selectedId = ref('')
const groupFilter = ref('all')

const NOTES_KEY = 'deepgoon:chem:notes'
const notes = ref<Note[]>([])
const noteDraft = ref('')
const notesLoaded = ref(false)

function groupLabel(group: string): string {
  return GROUP_LABELS[group] ?? group
}

function groupRank(group: string): number {
  const index = GROUP_ORDER.indexOf(group)
  return index === -1 ? GROUP_ORDER.length : index
}

function prettyName(name: string): string {
  return name.charAt(0).toUpperCase() + name.slice(1)
}

function reagentLabel(id: string): string {
  const name = reagentById.get(id)?.name ?? id
  const pretty = prettyName(name)
  const idMatchesName = id.toLowerCase() === name.replace(/\s+/g, '').toLowerCase()
  return idMatchesName ? pretty : `${pretty} (${id})`
}

function fmt(value: number, digits = 2): string {
  if (!Number.isFinite(value)) return '—'
  const factor = 10 ** digits
  const rounded = Math.round(value * factor) / factor
  const text = digits > 0
    ? rounded.toFixed(digits).replace(/0+$/, '').replace(/\.$/, '')
    : rounded.toFixed(0)
  return text.replace('.', ',')
}

function plural(count: number, one: string, few: string, many: string): string {
  const abs = Math.abs(count) % 100
  const last = abs % 10
  if (abs > 10 && abs < 20) return many
  if (last === 1) return one
  if (last > 1 && last < 5) return few
  return many
}

function positiveOr(value: number | string, fallback: number): number {
  const number = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(number) && number > 0 ? number : fallback
}

const flask = computed(() => positiveOr(flaskVolume.value, 100))
const target = computed(() => positiveOr(targetVolume.value, 30))

/** Все реагенты, которые можно получить хотя бы одной реакцией. */
const reactionsByProduct = computed(() => {
  const map = new Map<string, Reaction[]>()
  for (const reaction of reactions) {
    for (const productId of Object.keys(reaction.products)) {
      const list = map.get(productId)
      if (list) list.push(reaction)
      else map.set(productId, [reaction])
    }
  }
  return map
})

/** Опции выбора реагента, сгруппированные по группе первого рецепта. */
const reagentOptionGroups = computed(() => {
  const byGroup = new Map<string, { id: string, label: string }[]>()
  for (const [id, producedBy] of reactionsByProduct.value) {
    const firstReaction = producedBy[0]
    if (!firstReaction) continue
    const option = { id, label: reagentLabel(id) }
    const list = byGroup.get(firstReaction.group)
    if (list) list.push(option)
    else byGroup.set(firstReaction.group, [option])
  }

  return [...byGroup.entries()]
    .sort((a, b) => groupRank(a[0]) - groupRank(b[0]))
    .map(([group, options]) => ({
      group,
      label: groupLabel(group),
      options: options.sort((a, b) => a.label.localeCompare(b.label, 'ru')),
    }))
})

const recipeGroups = computed(() => reagentOptionGroups.value.map(entry => entry.group))

const selectedReagent = computed(() => (selectedId.value ? reagentById.get(selectedId.value) ?? null : null))
const selectedName = computed(() => (selectedReagent.value ? prettyName(selectedReagent.value.name) : ''))

const producedBy = computed(() => {
  if (!selectedId.value) return []
  return reactionsByProduct.value.get(selectedId.value) ?? []
})

const visibleReactions = computed(() => {
  if (groupFilter.value === 'all') return producedBy.value
  return producedBy.value.filter(reaction => reaction.group === groupFilter.value)
})

const filteredOut = computed(() => producedBy.value.length > 0 && visibleReactions.value.length === 0)

function requirementLabels(reaction: Reaction): string[] {
  const labels: string[] = []
  if (reaction.minTemp !== null && reaction.maxTemp !== null) {
    labels.push(`температура ${fmt(reaction.minTemp)}–${fmt(reaction.maxTemp)} K`)
  } else if (reaction.minTemp !== null) {
    labels.push(`нагреть до ${fmt(reaction.minTemp)} K`)
  } else if (reaction.maxTemp !== null) {
    labels.push(`не выше ${fmt(reaction.maxTemp)} K`)
  }
  if (reaction.mixer.length > 0) {
    labels.push(`оборудование: ${reaction.mixer.join(', ')}`)
  }
  return labels
}

const calculations = computed<RecipeCalc[]>(() => {
  const flaskSize = flask.value
  const desired = target.value

  return visibleReactions.value.flatMap((reaction) => {
    const yieldPerBatch = reaction.products[selectedId.value] ?? 0
    if (yieldPerBatch <= 0) return []

    const batches = Math.max(1, Math.ceil(Math.round((desired / yieldPerBatch) * 1e6) / 1e6))
    const inputPerBatch = Object.values(reaction.reactants).reduce((sum, amount) => sum + amount, 0)
    const productsPerBatch = Object.values(reaction.products).reduce((sum, amount) => sum + amount, 0)
    // Смесь занимает больший из объёмов: до реакции — ингредиенты, после — продукты.
    const batchVolume = Math.max(inputPerBatch, productsPerBatch)
    const totalVolume = batchVolume * batches
    const free = flaskSize - totalVolume
    const ingredients = Object.entries(reaction.reactants)
      .map(([id, amount]) => {
        const reagent = reagentById.get(id)
        const total = amount * batches
        return {
          id,
          name: reagent ? prettyName(reagent.name) : id,
          color: reagent?.color ?? null,
          perBatch: amount,
          total,
          share: totalVolume > 0 ? (total / totalVolume) * 100 : 0,
        }
      })
      .sort((a, b) => b.total - a.total)

    return [{
      reaction,
      yieldPerBatch,
      batches,
      produced: yieldPerBatch * batches,
      inputPerBatch,
      productsPerBatch,
      inputVolume: inputPerBatch * batches,
      productsVolume: productsPerBatch * batches,
      batchVolume,
      totalVolume,
      free,
      fits: totalVolume <= flaskSize + 1e-9,
      runs: totalVolume > 0 ? Math.ceil(totalVolume / flaskSize) : 1,
      ingredients,
    }]
  })
})

function resetSelection() {
  selectedId.value = ''
  groupFilter.value = 'all'
}

function isNote(value: unknown): value is Note {
  if (!value || typeof value !== 'object') return false
  const note = value as Partial<Note>
  return typeof note.id === 'string' && typeof note.text === 'string' && typeof note.createdAt === 'string'
}

onMounted(() => {
  if (!import.meta.client) return
  try {
    const raw = localStorage.getItem(NOTES_KEY)
    const parsed: unknown = raw ? JSON.parse(raw) : []
    if (Array.isArray(parsed)) notes.value = parsed.filter(isNote)
  } catch {
    notes.value = []
  }
  notesLoaded.value = true
})

watch(notes, (value) => {
  if (!import.meta.client || !notesLoaded.value) return
  try {
    localStorage.setItem(NOTES_KEY, JSON.stringify(value))
  } catch {
    // Хранилище может быть недоступно (приватный режим, лимит) — молча пропускаем.
  }
}, { deep: true })

function newId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function saveNote() {
  const text = noteDraft.value.trim()
  if (!text) return
  notes.value = [{ id: newId(), text, createdAt: new Date().toISOString() }, ...notes.value]
  noteDraft.value = ''
}

function removeNote(id: string) {
  notes.value = notes.value.filter(note => note.id !== id)
}

function formatDate(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString('ru-RU', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
}
</script>

<template>
  <div class="space-y-5">
    <header class="card bg-base-100 shadow-xl">
      <div class="card-body gap-2">
        <p class="font-mono text-xs uppercase tracking-[0.2em] text-primary">deepgoon · chem</p>
        <h1 class="card-title text-3xl">Химия</h1>
        <p class="max-w-2xl text-sm opacity-70">
          Считает, сколько реагентов нужно взять и сколько места останется в колбе, чтобы получить заданное количество вещества.
        </p>
        <p class="pt-1 text-xs opacity-50">
          {{ reactions.length }} рецептов · {{ reagents.length }} реагентов · {{ producibleCount }} можно сварить
        </p>
      </div>
    </header>

    <div class="grid items-start gap-5 lg:grid-cols-3">
      <section class="space-y-5 lg:col-span-2">
        <div class="card bg-base-100 shadow-xl">
          <div class="card-body gap-5">
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 class="card-title">Калькулятор варки</h2>
                <p class="text-sm opacity-60">Выберите реагент, объём колбы и желаемое количество.</p>
              </div>
              <button v-if="selectedId || groupFilter !== 'all'" class="btn btn-ghost btn-sm" @click="resetSelection">
                Сбросить
              </button>
            </div>

            <div class="grid gap-4 sm:grid-cols-3">
              <label class="flex flex-col gap-1.5">
                <span class="text-xs font-medium uppercase tracking-wide opacity-60">Объём колбы, mL</span>
                <input v-model.number="flaskVolume" type="number" min="1" step="1" inputmode="decimal" class="input w-full" />
              </label>
              <label class="flex flex-col gap-1.5">
                <span class="text-xs font-medium uppercase tracking-wide opacity-60">Нужно получить, mL</span>
                <input v-model.number="targetVolume" type="number" min="0.1" step="0.1" inputmode="decimal" class="input w-full" />
              </label>
              <label class="flex flex-col gap-1.5">
                <span class="text-xs font-medium uppercase tracking-wide opacity-60">Группа рецептов</span>
                <select v-model="groupFilter" class="select w-full">
                  <option value="all">Все группы</option>
                  <option v-for="group in recipeGroups" :key="group" :value="group">
                    {{ groupLabel(group) }}
                  </option>
                </select>
              </label>
              <label class="flex flex-col gap-1.5 sm:col-span-3">
                <span class="text-xs font-medium uppercase tracking-wide opacity-60">Реагент-продукт</span>
                <select v-model="selectedId" class="select w-full">
                  <option value="">Выберите реагент…</option>
                  <optgroup v-for="entry in reagentOptionGroups" :key="entry.group" :label="entry.label">
                    <option v-for="option in entry.options" :key="option.id" :value="option.id">
                      {{ option.label }}
                    </option>
                  </optgroup>
                </select>
              </label>
            </div>

            <div v-if="!selectedId" class="rounded-box border border-dashed border-base-300 px-4 py-10 text-center">
              <p class="text-sm opacity-60">Выберите реагент, чтобы увидеть расчёт.</p>
            </div>

            <div v-else-if="filteredOut" class="alert alert-warning">
              <div>
                <p class="font-medium">В группе «{{ groupLabel(groupFilter) }}» нет рецепта для «{{ selectedName }}».</p>
                <p class="text-sm opacity-70">
                  Этот реагент варят в других группах —
                  {{ producedBy.length }} {{ plural(producedBy.length, 'рецепт', 'рецепта', 'рецептов') }} всего.
                </p>
              </div>
              <button class="btn btn-sm btn-ghost" @click="groupFilter = 'all'">Показать все</button>
            </div>

            <div v-else-if="calculations.length === 0" class="alert alert-info">
              <span>Ни одна реакция не производит выбранный реагент.</span>
            </div>

            <template v-else>
              <div class="flex flex-wrap items-baseline justify-between gap-2 border-t border-base-300 pt-4">
                <p class="text-sm">
                  Для <span class="font-semibold">{{ selectedName }}</span>
                  найдено {{ visibleReactions.length }}
                  <template v-if="groupFilter !== 'all'">из {{ producedBy.length }}</template>
                  {{ plural(visibleReactions.length, 'рецепт', 'рецепта', 'рецептов') }}
                </p>
                <p class="text-xs opacity-50">1 ед. реагента ≈ 1 mL</p>
              </div>

              <article
                v-for="(calc, index) in calculations"
                :key="calc.reaction.id"
                class="space-y-4 rounded-box border border-base-300 p-4"
              >
                <div class="flex flex-wrap items-center gap-2">
                  <h3 class="text-sm font-semibold">Рецепт {{ index + 1 }}</h3>
                  <span class="badge badge-ghost badge-sm">{{ groupLabel(calc.reaction.group) }}</span>
                  <span class="font-mono text-[11px] opacity-40">{{ calc.reaction.id }}</span>
                  <span class="badge badge-primary badge-soft badge-sm ml-auto">
                    выход {{ fmt(calc.yieldPerBatch) }} mL
                  </span>
                </div>

                <div class="stats stats-vertical w-full bg-base-200 sm:stats-horizontal">
                  <div class="stat">
                    <div class="stat-title text-xs">Партий</div>
                    <div class="stat-value text-2xl tabular-nums">{{ fmt(calc.batches, 0) }}</div>
                    <div class="stat-desc">получится {{ fmt(calc.produced) }} mL</div>
                  </div>
                  <div class="stat">
                    <div class="stat-title text-xs">Объём партии</div>
                    <div class="stat-value text-2xl tabular-nums">
                      {{ fmt(calc.batchVolume) }} <span class="text-sm font-normal opacity-60">mL</span>
                    </div>
                    <div class="stat-desc">
                      ингредиенты {{ fmt(calc.inputPerBatch) }} → продукты {{ fmt(calc.productsPerBatch) }} mL
                    </div>
                  </div>
                  <div class="stat">
                    <div class="stat-title text-xs">Свободно в колбе</div>
                    <div class="stat-value text-2xl tabular-nums" :class="calc.fits ? '' : 'text-error'">
                      {{ fmt(calc.free) }} <span class="text-sm font-normal opacity-60">mL</span>
                    </div>
                    <div class="stat-desc">из {{ fmt(flask) }} mL · занято {{ fmt(calc.totalVolume) }}</div>
                  </div>
                  <div class="stat">
                    <div class="stat-title text-xs">Статус</div>
                    <div class="stat-value text-lg" :class="calc.fits ? 'text-success' : 'text-error'">
                      {{ calc.fits ? 'Помещается' : 'Не помещается' }}
                    </div>
                    <div class="stat-desc">все ингредиенты в один заход</div>
                  </div>
                </div>

                <div v-if="!calc.fits" class="alert alert-error alert-soft">
                  <span class="text-sm">
                    Смеси {{ fmt(calc.totalVolume) }} mL при колбе {{ fmt(flask) }} mL.
                    Разделите на {{ calc.runs }}
                    {{ plural(calc.runs, 'заход', 'захода', 'заходов') }} — иначе часть реагента не поместится.
                  </span>
                </div>

                <div class="overflow-x-auto">
                  <table class="table table-zebra table-sm">
                    <thead>
                      <tr>
                        <th>Ингредиент</th>
                        <th class="text-right">На реакцию, mL</th>
                        <th class="text-right">Всего, mL</th>
                        <th class="text-right">Доля объёма</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="ingredient in calc.ingredients" :key="ingredient.id">
                        <td>
                          <div class="flex items-center gap-2.5">
                            <span
                              v-if="ingredient.color"
                              class="size-2.5 shrink-0 rounded-full ring-1 ring-base-content/20"
                              :style="{ backgroundColor: ingredient.color }"
                              :title="ingredient.color"
                            />
                            <span v-else class="size-2.5 shrink-0 rounded-full border border-dashed border-base-content/30" />
                            <div class="min-w-0">
                              <div class="font-medium">{{ ingredient.name }}</div>
                              <div class="font-mono text-[10px] opacity-50">{{ ingredient.id }}</div>
                            </div>
                          </div>
                        </td>
                        <td class="text-right tabular-nums">{{ fmt(ingredient.perBatch) }}</td>
                        <td class="text-right font-semibold tabular-nums">{{ fmt(ingredient.total) }}</td>
                        <td class="text-right tabular-nums opacity-70">{{ fmt(ingredient.share, 1) }}%</td>
                      </tr>
                    </tbody>
                    <tfoot v-if="calc.ingredients.length > 1">
                      <tr>
                        <th>Итого</th>
                        <th class="text-right tabular-nums">{{ fmt(calc.inputPerBatch) }}</th>
                        <th class="text-right tabular-nums">{{ fmt(calc.inputVolume) }}</th>
                        <th />
                      </tr>
                    </tfoot>
                  </table>
                </div>

                <p v-if="calc.productsPerBatch > calc.inputPerBatch + 1e-9" class="text-[11px] opacity-50">
                  После реакции смеси станет больше: {{ fmt(calc.productsPerBatch) }} mL на партию вместо
                  {{ fmt(calc.inputPerBatch) }} mL — расчёт колбы идёт по большему объёму.
                </p>

                <div v-if="requirementLabels(calc.reaction).length" class="flex flex-wrap items-center gap-2 text-xs">
                  <span class="opacity-60">Требования:</span>
                  <span
                    v-for="label in requirementLabels(calc.reaction)"
                    :key="label"
                    class="badge badge-warning badge-soft badge-sm"
                  >
                    {{ label }}
                  </span>
                </div>
              </article>
            </template>
          </div>
        </div>

        <div class="card border border-dashed border-base-300 bg-base-100 shadow-xl">
          <div class="card-body gap-2">
            <div class="flex items-center justify-between gap-3">
              <h2 class="card-title text-lg">Рецепты по группам</h2>
              <span class="badge badge-ghost badge-sm">скоро</span>
            </div>
            <p class="text-sm opacity-60">
              Здесь появятся списки рецептов по группам, избранное и сравнение вариантов варки.
            </p>
          </div>
        </div>
      </section>

      <aside class="lg:sticky lg:top-5">
        <div class="card bg-base-100 shadow-xl">
          <div class="card-body gap-3">
            <div class="flex items-center justify-between gap-3">
              <h2 class="card-title text-lg">Заметки</h2>
              <span class="badge badge-ghost badge-sm">{{ notes.length }}</span>
            </div>
            <p class="text-sm opacity-60">Быстрые рецепты и напоминания. Хранятся только в этом браузере.</p>

            <textarea
              v-model="noteDraft"
              class="textarea h-28 w-full"
              placeholder="Например: для 30 mL бикаридина — 10 mL амбузола, 10 mL…"
              @keydown.ctrl.enter.prevent="saveNote"
            />

            <div class="flex items-center justify-between gap-2">
              <span class="text-[11px] opacity-50">Ctrl + Enter — сохранить</span>
              <button class="btn btn-primary btn-sm" :disabled="!noteDraft.trim()" @click="saveNote">
                Сохранить
              </button>
            </div>

            <div v-if="notes.length" class="border-t border-base-300">
              <div v-for="note in notes" :key="note.id" class="flex items-start gap-2 border-b border-base-300 py-3">
                <div class="min-w-0 flex-1">
                  <p class="text-sm break-words whitespace-pre-line">{{ note.text }}</p>
                  <p class="mt-1 text-[11px] opacity-50">{{ formatDate(note.createdAt) }}</p>
                </div>
                <button
                  class="btn btn-ghost btn-xs opacity-60 hover:opacity-100"
                  aria-label="Удалить заметку"
                  @click="removeNote(note.id)"
                >
                  Удалить
                </button>
              </div>
            </div>

            <div v-else class="rounded-box border border-dashed border-base-300 px-3 py-6 text-center">
              <p class="text-xs opacity-50">Пока нет заметок.</p>
            </div>
          </div>
        </div>
      </aside>
    </div>
  </div>
</template>
