<script setup lang="ts">
/**
 * /chem — калькулятор варки химии для SS14 (DeepLagoon).
 *
 * Данные: app/data/chem.json собирается скриптом scripts/build-chem-data.py
 * из прототипов Resources/ (реакции + реагенты). Русские и английские названия
 * реагентов лежат в app/data/reagent-names.json.
 *
 * Ключевые понятия:
 *  - партия (batch) — один запуск реакции по рецепту;
 *  - выход партии — сколько продукта даёт один запуск;
 *  - шаг перелива — минимальный объём, которым игрок может налить реагент
 *    (1 mL или 5 mL, если включён «Перелив ×5»). Меньше точной потребности
 *    налить нельзя, поэтому все объёмы округляются вверх.
 *
 * Порядок разделов ниже: типы → данные и состояние → форматирование →
 * расчёты → комбобокс выбора реагента → дерево подрецептов → хуки.
 */
import chem from '~/data/chem.json'
import reagentNamesData from '~/data/reagent-names.json'

/** Типы повторяют структуру app/data/chem.json (см. scripts/build-chem-data.py). */
type Reagent = {
  id: string
  name: string
  color: string | null
}

type ReagentNames = Record<string, { en: string; ru: string }>

const reagentNames = reagentNamesData as ReagentNames

type Reaction = {
  id: string
  group: string
  reactants: Record<string, number>
  products: Record<string, number>
  minTemp: number | null
  maxTemp: number | null
  mixer: string[]
}

type IngredientRow = {
  id: string
  name: string
  nameEn: string
  color: string | null
  perBatch: number
  /** Столько реагента реально нужно по реакции (может быть дробным). */
  exactTotal: number
  /** Столько придётся налить с учётом шага перелива — всегда целое или кратное шагу. */
  total: number
  /** Запас сверх точной потребности: total − exactTotal. */
  extra: number
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
  /** Шаг перелива, по которому округлены объёмы. */
  step: number
  /** Суммарный запас из-за округления вверх. */
  pouredExtra: number
  ingredients: IngredientRow[]
}

type PickerOption = {
  id: string
  ru: string
  en: string
  color: string | null
}

type PickerGroup = {
  group: string
  label: string
  options: PickerOption[]
}

/** Строка плоского дерева подрецептов: реагент или один из вариантов его варки. */
type TreeRow = {
  key: string
  /** Длина цепочки реагентов до этой строки — только она расходует бюджет глубины. */
  chainDepth: number
  /** Отступ строки: строки-варианты сдвигаются на уровень вправо, но цепочку не удлиняют. */
  visualDepth: number
  kind: 'reagent' | 'variant'
  id: string
  name: string
  color: string | null
  /** Для реагента — сколько нужно на этом уровне, для варианта — выход за партию. */
  amount: number
  /** Сколько партий этого рецепта нужно, чтобы закрыть потребность уровня. */
  batches: number
  /** Группа рецепта (только у вариантов). */
  group: string
  requirements: string[]
  cycle: boolean
  tooDeep: boolean
  /** Есть ли смысл раскрывать требования по клику. */
  expandable: boolean
}

type RecipeTree = {
  rows: TreeRow[]
  truncated: boolean
}

type TreeContext = {
  rows: TreeRow[]
}

/** Сохранённый рецепт: реагент, конкретная реакция и нужный объём. Живёт в localStorage. */
type SavedRecipe = {
  key: string
  reagentId: string
  reactionId: string
  target: number
}

type SavedEntry = {
  saved: SavedRecipe
  calc: RecipeCalc
  tree: RecipeTree
}

const reagents = chem.reagents as Reagent[]
const reactions = chem.reactions as Reaction[]

/* -------------------------------- Данные --------------------------------- */

/** Человекочитаемые названия групп рецептов; порядок ключей задаёт сортировку в списках. */
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

/* ------------------------------- Состояние ------------------------------- */

// number | string, чтобы поле ввода не сбрасывалось, пока пользователь его очищает.
// В расчётах значения прогоняются через positiveOr/flask/target.
const flaskVolume = ref<number | string>(100)
const targetVolume = ref<number | string>(30)
const selectedId = ref('')
const groupFilter = ref('all')
/** Показывает дерево подрецептов под каждым вариантом варки. */
const advancedMode = ref(false)
/** Кратно 5: в химмастере/переливании удобнее наливать пятёрками, а не по единице. */
const snapFive = ref(false)

const pickerOpen = ref(false)
const pickerQuery = ref('')
const pickerActive = ref(0)
const pickerRoot = ref<HTMLElement | null>(null)
const pickerTrigger = ref<HTMLElement | null>(null)
const pickerSearch = ref<HTMLInputElement | null>(null)
const pickerList = ref<HTMLElement | null>(null)

/** Ключи строк дерева, у которых раскрыты требования рецепта. */
const openTreeRows = ref<Set<string>>(new Set())
/** Насколько глубоко раскрывать цепочку подрецептов (1 — только первый уровень). */
const treeDepthLimit = ref(1)

/** Сохранённые рецепты из правой панели (переживают перезагрузку). */
const SAVED_STORAGE_KEY = 'chem:saved-recipes'
const savedRecipes = ref<SavedRecipe[]>([])
/** Ключи сохранённых рецептов, развёрнутых в панели. */
const savedOpen = ref<Set<string>>(new Set())
/** Глубина генерации подрецептов в правой панели. */
const savedDepthLimit = ref(2)
/** Явно развёрнутые строки дерева; по умолчанию все узлы со потомками свёрнуты. */
const expandedTreeRows = ref<Set<string>>(new Set())

/** Название группы: неизвестные группы показываем сырым id, а не теряем. */
function groupLabel(group: string): string {
  return GROUP_LABELS[group] ?? group
}

/** Индекс группы для сортировки; незнакомые уходят в конец. */
function groupRank(group: string): number {
  const index = GROUP_ORDER.indexOf(group)
  return index === -1 ? GROUP_ORDER.length : index
}

/** Названия RU/EN с фолбэком на служебное имя из chem.json. */
function getReagentNames(id: string): { ru: string; en: string } {
  const fromMap = reagentNames[id]
  if (fromMap) return fromMap
  const fallback = reagentById.get(id)?.name ?? id
  return { ru: fallback, en: fallback }
}

function reagentSearchText(id: string): string {
  const n = getReagentNames(id)
  return `${n.ru} ${n.en} ${id}`.toLowerCase()
}

/* ----------------------------- Форматирование ---------------------------- */

/**
 * Число для интерфейса: до `digits` знаков, без хвостовых нулей, с запятой.
 * Нечисла показываем прочерком, чтобы таблица не ломалась.
 */
function fmt(value: number, digits = 2): string {
  if (!Number.isFinite(value)) return '—'
  const factor = 10 ** digits
  const rounded = Math.round(value * factor) / factor
  const text = digits > 0
    ? rounded.toFixed(digits).replace(/0+$/, '').replace(/\.$/, '')
    : rounded.toFixed(0)
  return text.replace('.', ',')
}

/** Русский плюрализ: plural(2, 'партия', 'партии', 'партий') → 'партии'. */
function plural(count: number, one: string, few: string, many: string): string {
  const abs = Math.abs(count) % 100
  const last = abs % 10
  if (abs > 10 && abs < 20) return many
  if (last === 1) return one
  if (last > 1 && last < 5) return few
  return many
}

/** Приводит ввод к положительному числу; пустое/битое значение заменяет дефолтом. */
function positiveOr(value: number | string, fallback: number): number {
  const number = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(number) && number > 0 ? number : fallback
}

/**
 * Округление вверх до шага перелива. Недоливать нельзя — реакция не пойдёт,
 * поэтому 17 при шаге 5 превращается в 20 (а не в 15), а 0,22 при шаге 1 — в 1.
 */
function ceilToStep(value: number, step: number): number {
  if (!Number.isFinite(value) || value <= 0) return 0
  const normalized = Math.max(1, Math.round(step))
  return Math.ceil((value - 1e-9) / normalized) * normalized
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
const reagentOptionGroups = computed<PickerGroup[]>(() => {
  const byGroup = new Map<string, PickerOption[]>()
  for (const [id, produced] of reactionsByProduct.value) {
    const firstReaction = produced[0]
    if (!firstReaction) continue
    const names = getReagentNames(id)
    const option = { id, ru: names.ru, en: names.en, color: reagentById.get(id)?.color ?? null }
    const list = byGroup.get(firstReaction.group)
    if (list) list.push(option)
    else byGroup.set(firstReaction.group, [option])
  }

  return [...byGroup.entries()]
    .sort((a, b) => groupRank(a[0]) - groupRank(b[0]))
    .map(([group, options]) => ({
      group,
      label: groupLabel(group),
      options: options.sort((a, b) => a.ru.localeCompare(b.ru, 'ru')),
    }))
})

const recipeGroups = computed(() => reagentOptionGroups.value.map(entry => entry.group))

const selectedReagent = computed(() => (selectedId.value ? reagentById.get(selectedId.value) ?? null : null))
const selectedName = computed(() => (selectedId.value ? getReagentNames(selectedId.value).ru : ''))
const selectedNameEn = computed(() => (selectedId.value ? getReagentNames(selectedId.value).en : ''))

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

/**
 * Расчёт одного рецепта на нужный объём. Вынесен отдельной функцией, потому что
 * его же использует правая панель сохранённых рецептов.
 */
function computeRecipe(
  reaction: Reaction,
  productId: string,
  desired: number,
  flaskSize: number,
  step: number,
): RecipeCalc | null {
  const yieldPerBatch = reaction.products[productId] ?? 0
  if (yieldPerBatch <= 0) return null

  // Минимальное число партий, которое закрывает нужный объём.
  const batches = Math.max(1, Math.ceil(Math.round((desired / yieldPerBatch) * 1e6) / 1e6))
  const inputPerBatch = Object.values(reaction.reactants).reduce((sum, amount) => sum + amount, 0)
  const productsPerBatch = Object.values(reaction.products).reduce((sum, amount) => sum + amount, 0)

  // Наливаем кратными шагу объёмами: точную потребность округляем вверх.
  const ingredients = Object.entries(reaction.reactants)
    .map(([id, amount]) => {
      const reagent = reagentById.get(id)
      const names = getReagentNames(id)
      const exactTotal = amount * batches
      const total = ceilToStep(exactTotal, step)
      return {
        id,
        name: names.ru,
        nameEn: names.en,
        color: reagent?.color ?? null,
        perBatch: amount,
        exactTotal,
        total,
        extra: total - exactTotal,
        share: 0,
      }
    })
    .sort((a, b) => b.total - a.total)

  const pouredInput = ingredients.reduce((sum, ingredient) => sum + ingredient.total, 0)
  const pouredExtra = ingredients.reduce((sum, ingredient) => sum + ingredient.extra, 0)
  const productsVolume = productsPerBatch * batches
  // Излишки, которые не прореагируют, остаются в колбе: считаем и до, и после реакции.
  const afterVolume = productsVolume + pouredExtra
  const totalVolume = Math.max(pouredInput, afterVolume)
  const free = flaskSize - totalVolume

  for (const ingredient of ingredients) {
    ingredient.share = totalVolume > 0 ? (ingredient.total / totalVolume) * 100 : 0
  }

  return {
    reaction,
    yieldPerBatch,
    batches,
    produced: yieldPerBatch * batches,
    inputPerBatch,
    productsPerBatch,
    inputVolume: pouredInput,
    productsVolume,
    batchVolume: Math.max(inputPerBatch, productsPerBatch),
    totalVolume,
    free,
    fits: totalVolume <= flaskSize + 1e-9,
    runs: totalVolume > 0 ? Math.ceil(totalVolume / flaskSize) : 1,
    step,
    pouredExtra,
    ingredients,
  }
}

/**
 * Основной расчёт по каждому подходящему рецепту (фильтр по группе уже применён).
 *
 * Алгоритм:
 *  1. Партии = ceil(нужно / выход) — минимальное число запусков, дающее цель.
 *  2. Объёмы ингредиентов = количество на партию × партии, затем округление
 *     вверх до шага перелива (ceilToStep). Именно эти числа игрок наливает.
 *  3. Объём в колбе — пик из «до реакции» (налитые ингредиенты) и «после»
 *     (продукты + неиспользованный излишек): излишек остаётся в растворе.
 */
const calculations = computed<RecipeCalc[]>(() => {
  const step = snapFive.value ? 5 : 1
  return visibleReactions.value
    .map(reaction => computeRecipe(reaction, selectedId.value, target.value, flask.value, step))
    .filter((calc): calc is RecipeCalc => calc !== null)
})

/* ------------------------------- Комбобокс ------------------------------- */
/**
 * Самодостаточный combobox без сторонних библиотек.
 * Роли/aria расставлены по паттерну WAI-ARIA: триггер с role="combobox",
 * список role="listbox", опции role="option", клавиатура через aria-activedescendant.
 * Фокус остаётся в поле поиска — поэтому навигация стрелками ведётся вручную.
 */

function optionDomId(id: string): string {
  return `chem-reagent-option-${id}`
}

/** Нормализация для поиска: без регистра, пробелов, дефисов и подчёркиваний. */
function normalizeSearch(value: string): string {
  return value.toLowerCase().replace(/[\s\-_]+/g, '')
}

const pickerGroups = computed<PickerGroup[]>(() => {
  const query = normalizeSearch(pickerQuery.value)
  if (!query) return reagentOptionGroups.value

  return reagentOptionGroups.value
    .map(entry => ({
      ...entry,
      options: entry.options.filter(option => {
        const hay = normalizeSearch(`${option.ru} ${option.en} ${option.id}`)
        return hay.includes(query)
      }),
    }))
    .filter(entry => entry.options.length > 0)
})

const pickerOptions = computed(() => pickerGroups.value.flatMap(entry => entry.options))
const activeOption = computed(() => pickerOptions.value[pickerActive.value] ?? null)
const activeOptionDomId = computed(() => (activeOption.value ? optionDomId(activeOption.value.id) : ''))

function scrollActiveOption() {
  if (!import.meta.client) return
  void nextTick(() => {
    const list = pickerList.value
    const active = list?.querySelector<HTMLElement>('[data-active="true"]')
    if (!list || !active) return
    // Прокручиваем только список, чтобы не дёргать страницу; запас сверху — под липкий заголовок группы.
    const headerHeight = 20
    const listRect = list.getBoundingClientRect()
    const activeRect = active.getBoundingClientRect()
    if (activeRect.top - headerHeight < listRect.top) {
      list.scrollTop -= listRect.top - activeRect.top + headerHeight
    } else if (activeRect.bottom > listRect.bottom) {
      list.scrollTop += activeRect.bottom - listRect.bottom
    }
  })
}

function clampActive() {
  const size = pickerOptions.value.length
  if (size === 0) {
    pickerActive.value = 0
    return
  }
  if (pickerActive.value < 0) pickerActive.value = size - 1
  else if (pickerActive.value >= size) pickerActive.value = 0
}

function openPicker(initialQuery = '') {
  const wasOpen = pickerOpen.value
  pickerQuery.value = initialQuery
  pickerOpen.value = true
  const flat = pickerOptions.value
  const selectedIndex = !initialQuery && selectedId.value
    ? flat.findIndex(option => option.id === selectedId.value)
    : -1
  pickerActive.value = selectedIndex >= 0 ? selectedIndex : 0
  if (!wasOpen) {
    void nextTick(() => {
      pickerSearch.value?.focus()
      scrollActiveOption()
    })
  }
}

function closePicker(restoreFocus = false) {
  if (!pickerOpen.value) return
  pickerOpen.value = false
  pickerQuery.value = ''
  if (restoreFocus) void nextTick(() => pickerTrigger.value?.focus())
}

function togglePicker() {
  if (pickerOpen.value) closePicker()
  else openPicker()
}

function selectReagent(id: string) {
  selectedId.value = id
  closePicker(true)
}

/** Сброс подсветки и прокрутки списка при вводе запроса. */
function onSearchInput() {
  pickerActive.value = 0
  if (pickerList.value) pickerList.value.scrollTop = 0
}

function clearSelection() {
  selectedId.value = ''
  pickerActive.value = 0
  closePicker(true)
}

function moveActive(step: number) {
  pickerActive.value += step
  clampActive()
  scrollActiveOption()
}

function setActive(id: string) {
  const index = pickerOptions.value.findIndex(option => option.id === id)
  if (index >= 0) pickerActive.value = index
}

function onTriggerKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    if (pickerOpen.value) {
      event.preventDefault()
      closePicker()
    }
    return
  }
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault()
    if (!pickerOpen.value) openPicker()
    else moveActive(event.key === 'ArrowDown' ? 1 : -1)
    return
  }
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    if (!pickerOpen.value) openPicker()
    else if (activeOption.value) selectReagent(activeOption.value.id)
    return
  }
  if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
    event.preventDefault()
    openPicker(event.key)
  }
}

function onSearchKeydown(event: KeyboardEvent) {
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault()
    moveActive(event.key === 'ArrowDown' ? 1 : -1)
    return
  }
  if (event.key === 'Home' || event.key === 'End') {
    event.preventDefault()
    pickerActive.value = event.key === 'Home' ? 0 : pickerOptions.value.length - 1
    clampActive()
    scrollActiveOption()
    return
  }
  if (event.key === 'Enter') {
    event.preventDefault()
    if (activeOption.value) selectReagent(activeOption.value.id)
    return
  }
  if (event.key === 'Escape') {
    event.preventDefault()
    closePicker(true)
    return
  }
  if (event.key === 'Tab') closePicker()
}

function onDocumentPointerDown(event: PointerEvent) {
  if (!pickerOpen.value) return
  const root = pickerRoot.value
  if (root && event.target instanceof Node && root.contains(event.target)) return
  closePicker()
}

/* ----------------------------- Подрецепты ------------------------------- */

/** Потолок строк дерева: защита от «простыни» и от взрыва рекурсии на больших цепочках. */
const MAX_TREE_ROWS = 200

/**
 * Сколько партий рецепта нужно, чтобы получить `needed`.
 * Округление до 1e-6 гасит ошибки float (например, 0.3 / 0.1 = 2.9999999996).
 */
function batchCount(needed: number, yieldPerBatch: number): number {
  if (yieldPerBatch <= 0) return 1
  const raw = Math.round((needed / yieldPerBatch) * 1e6) / 1e6
  return Math.max(1, Math.ceil(raw))
}

/**
 * Раскладывает подрецепты в плоский список строк: рекурсия в script, а не в шаблоне.
 * Циклы в цепочке и превышение глубины помечаются бейджами и дальше не раскрываются,
 * общий размер дерева ограничен, чтобы страница не превращалась в простыню.
 * Бюджет глубины считает только цепочку реагентов: строки-варианты («у реагента несколько
 * рецептов») сдвигаются вправо для наглядности, но уровень вложенности не тратят.
 * MAX_TREE_ROWS остаётся главным ограничителем.
 */
function buildTreeNode(
  context: TreeContext,
  reagentId: string,
  needed: number,
  chain: readonly string[],
  chainDepth: number,
  visualDepth: number,
  keyPrefix: string,
  depthLimit: number,
): void {
  if (context.rows.length >= MAX_TREE_ROWS) return

  const step = snapFive.value ? 5 : 1
  // Налить меньше точной потребности нельзя, поэтому объём подрецепта тоже округляем вверх.
  const required = ceilToStep(needed, step)
  const reagent = reagentById.get(reagentId)
  const producers = reactionsByProduct.value.get(reagentId) ?? []
  const cycle = chain.includes(reagentId)
  // Бейдж «глубина» — только там, где действительно есть что раскрывать, но бюджет кончился.
  const tooDeep = !cycle && producers.length > 0 && chainDepth >= depthLimit
  const canExpand = !cycle && !tooDeep && producers.length > 0
  const names = getReagentNames(reagentId)
  const base = {
    key: keyPrefix,
    chainDepth,
    visualDepth,
    id: reagentId,
    name: names.ru,
    color: reagent?.color ?? null,
  }

  const singleProducer = canExpand && producers.length === 1 ? producers[0] : undefined

  if (singleProducer) {
    const yieldPerBatch = singleProducer.products[reagentId] ?? 0
    const batches = batchCount(required, yieldPerBatch)
    const requirements = requirementLabels(singleProducer)
    context.rows.push({
      ...base,
      kind: 'reagent',
      amount: required,
      batches,
      group: singleProducer.group,
      requirements,
      cycle: false,
      tooDeep: false,
      expandable: requirements.length > 0,
    })

    for (const [childId, amount] of Object.entries(singleProducer.reactants)) {
      buildTreeNode(
        context,
        childId,
        amount * batches,
        [...chain, reagentId],
        chainDepth + 1,
        visualDepth + 1,
        `${keyPrefix}/${childId}`,
        depthLimit,
      )
    }
    return
  }

  context.rows.push({
    ...base,
    kind: 'reagent',
    amount: required,
    batches: 1,
    group: '',
    requirements: [],
    cycle,
    tooDeep,
    expandable: false,
  })

  if (!canExpand) return

  const nextChain = [...chain, reagentId]
  producers.forEach((reaction, index) => {
    if (context.rows.length >= MAX_TREE_ROWS) return
    const yieldPerBatch = reaction.products[reagentId] ?? 0
    const batches = batchCount(required, yieldPerBatch)
    const variantKey = `${keyPrefix}~${reaction.id}`
    context.rows.push({
      key: variantKey,
      chainDepth,
      visualDepth: visualDepth + 1,
      kind: 'variant',
      id: reaction.id,
      name: `Вариант ${index + 1}`,
      color: null,
      amount: yieldPerBatch,
      batches,
      group: reaction.group,
      requirements: requirementLabels(reaction),
      cycle: false,
      tooDeep: false,
      expandable: false,
    })

    for (const [childId, amount] of Object.entries(reaction.reactants)) {
      buildTreeNode(
        context,
        childId,
        amount * batches,
        nextChain,
        chainDepth + 1,
        visualDepth + 2,
        `${variantKey}/${childId}`,
        depthLimit,
      )
    }
  })
}

/** Дерево подрецептов по каждому рецепту расчёта; пересчитывается только при смене параметров. */
const advancedTrees = computed<Record<string, RecipeTree>>(() => {
  const result: Record<string, RecipeTree> = {}
  if (!advancedMode.value) return result

  const rootChain = selectedId.value ? [selectedId.value] : []
  for (const calc of calculations.value) {
    const context: TreeContext = { rows: [] }
    for (const ingredient of calc.ingredients) {
      if (ingredient.id === selectedId.value) continue
      buildTreeNode(context, ingredient.id, ingredient.total, rootChain, 0, 0, `${calc.reaction.id}:${ingredient.id}`, treeDepthLimit.value)
    }
    result[calc.reaction.id] = { rows: context.rows, truncated: context.rows.length >= MAX_TREE_ROWS }
  }
  return result
})

/** Раскрытие/скрытие требований строки. Set заменяем целиком, чтобы сработала реактивность. */
function toggleTreeRow(key: string) {
  const next = new Set(openTreeRows.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  openTreeRows.value = next
}

/** После смены глубины старые ключи строк невалидны — сворачиваем всё. */
watch(treeDepthLimit, () => {
  openTreeRows.value = new Set()
})

/* --------------------------- Сохранённые рецепты -------------------------- */

/** Пересчёт сохранённых рецептов и компактное дерево подрецептов для правой панели. */
const savedEntries = computed<SavedEntry[]>(() => {
  const step = snapFive.value ? 5 : 1
  return savedRecipes.value.flatMap((saved) => {
    const reaction = reactions.find(item => item.id === saved.reactionId)
    if (!reaction) return []
    const calc = computeRecipe(reaction, saved.reagentId, saved.target, flask.value, step)
    if (!calc) return []
    const context: TreeContext = { rows: [] }
    for (const ingredient of calc.ingredients) {
      buildTreeNode(
        context,
        ingredient.id,
        ingredient.total,
        [saved.reagentId],
        0,
        0,
        `${saved.key}:${ingredient.id}`,
        savedDepthLimit.value,
      )
    }
    return [{ saved, calc, tree: { rows: context.rows, truncated: context.rows.length >= MAX_TREE_ROWS } }]
  })
})

/** Совпадает ли рецепт с текущим расчётом: тот же реагент, реакция и объём. */
function isRecipeSaved(calc: RecipeCalc): boolean {
  return savedRecipes.value.some(saved =>
    saved.reactionId === calc.reaction.id
    && saved.reagentId === selectedId.value
    && Math.abs(saved.target - target.value) < 1e-9,
  )
}

function saveRecipe(calc: RecipeCalc) {
  if (!selectedId.value || isRecipeSaved(calc)) return
  const saved: SavedRecipe = {
    key: `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`,
    reagentId: selectedId.value,
    reactionId: calc.reaction.id,
    target: target.value,
  }
  savedRecipes.value = [...savedRecipes.value, saved]
  savedOpen.value = new Set([...savedOpen.value, saved.key])
}

function removeSaved(key: string) {
  savedRecipes.value = savedRecipes.value.filter(saved => saved.key !== key)
  const next = new Set(savedOpen.value)
  next.delete(key)
  savedOpen.value = next
}

function clearSaved() {
  savedRecipes.value = []
  savedOpen.value = new Set()
}

function toggleSavedOpen(key: string) {
  const next = new Set(savedOpen.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  savedOpen.value = next
}

/** Загружает сохранённый рецепт обратно в калькулятор. */
function loadSaved(saved: SavedRecipe) {
  selectedId.value = saved.reagentId
  targetVolume.value = saved.target
  groupFilter.value = 'all'
}

/** Обновляет целевой объём сохранённого рецепта; пустое/битое значение игнорируем. */
function updateSavedTarget(key: string, event: Event) {
  const input = event.target as HTMLInputElement | null
  const next = Number(input?.value)
  if (!Number.isFinite(next) || next <= 0) {
    // Возвращаем последнее валидное значение, чтобы поле не залипало пустым.
    if (input) {
      const current = savedRecipes.value.find(saved => saved.key === key)
      if (current) input.value = String(current.target)
    }
    return
  }
  savedRecipes.value = savedRecipes.value.map(saved =>
    saved.key === key ? { ...saved, target: next } : saved,
  )
}

function savedReagentName(id: string): string {
  return getReagentNames(id).ru
}

/** Есть ли у строки потомки — определяется по путям ключей, без отдельной иерархии. */
function savedRowHasChildren(rows: TreeRow[], key: string): boolean {
  return rows.some(row => row.key !== key
    && (row.key.startsWith(`${key}/`) || row.key.startsWith(`${key}~`)))
}

/** В дереве по умолчанию свёрнуто всё ниже 1-го уровня: видны только корневые строки. */
function isSavedRowCollapsed(row: TreeRow, rows: TreeRow[]): boolean {
  if (!savedRowHasChildren(rows, row.key)) return false
  if (expandedTreeRows.value.has(row.key)) return false
  return true
}

/** Свёрнутая строка дерева скрывает всех потомков (дочерние реагенты и варианты). */
function visibleSavedRows(tree: RecipeTree): TreeRow[] {
  const rows = tree.rows
  return rows.filter((row) => {
    for (const ancestor of rows) {
      if (ancestor.key === row.key) continue
      if (!row.key.startsWith(`${ancestor.key}/`) && !row.key.startsWith(`${ancestor.key}~`)) continue
      if (isSavedRowCollapsed(ancestor, rows)) return false
    }
    return true
  })
}

function toggleSavedRow(row: TreeRow, rows: TreeRow[]) {
  if (!savedRowHasChildren(rows, row.key)) return
  const nextExpanded = new Set(expandedTreeRows.value)
  if (nextExpanded.has(row.key)) nextExpanded.delete(row.key)
  else nextExpanded.add(row.key)
  expandedTreeRows.value = nextExpanded
}

/** Смена глубины меняет набор строк — явные раскрытия сбрасываем. */
watch(savedDepthLimit, () => {
  expandedTreeRows.value = new Set()
})

/** Сохраняем в localStorage при каждом изменении списка. */
watch(savedRecipes, (value) => {
  if (!import.meta.client) return
  try {
    localStorage.setItem(SAVED_STORAGE_KEY, JSON.stringify(value))
  } catch {
    // Приватный режим или квота: работаем без сохранения, интерфейс не ломаем.
  }
}, { deep: true })

/** Сброс выбора и фильтра к исходному состоянию. */
function resetSelection() {
  selectedId.value = ''
  groupFilter.value = 'all'
  closePicker()
}

// Закрытие по клику вне комбобокса; слушатель только в браузере (SSR его не имеет).
onMounted(() => {
  if (!import.meta.client) return
  document.addEventListener('pointerdown', onDocumentPointerDown)
  try {
    const stored = localStorage.getItem(SAVED_STORAGE_KEY)
    if (!stored) return
    const parsed: unknown = JSON.parse(stored)
    if (!Array.isArray(parsed)) return
    savedRecipes.value = parsed.filter((item): item is SavedRecipe => (
      typeof item === 'object' && item !== null
      && typeof (item as SavedRecipe).key === 'string'
      && typeof (item as SavedRecipe).reagentId === 'string'
      && typeof (item as SavedRecipe).reactionId === 'string'
      && typeof (item as SavedRecipe).target === 'number'
    ))
  } catch {
    // Битый localStorage не должен ломать страницу.
  }
})

onBeforeUnmount(() => {
  if (import.meta.client) document.removeEventListener('pointerdown', onDocumentPointerDown)
})
</script>

<template>
  <div class="space-y-5">
    <!-- Шапка: назначение страницы и счётчики из данных. -->
    <header class="flex flex-wrap items-center gap-x-3 gap-y-1 px-1">
      <h1 class="text-xl font-bold leading-tight">Химия</h1>
      <p class="text-xs opacity-60">
        Расчёт реагентов и остатка в колбе.
      </p>
      <p class="ml-auto text-[11px] tabular-nums opacity-50">
        {{ reactions.length }} рецептов · {{ reagents.length }} реагентов · {{ producibleCount }} можно сварить
      </p>
    </header>

    <div class="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_21rem]">
      <section class="min-w-0 space-y-5">
        <div class="card bg-base-100 shadow-xl">
          <div class="card-body gap-5">
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 class="card-title">Калькулятор варки</h2>
                <p class="text-sm opacity-60">Выберите реагент, объём колбы и желаемое количество.</p>
              </div>
              <div class="flex flex-wrap items-center gap-3">
                <label
                  class="flex cursor-pointer items-center gap-2 text-xs"
                  title="Округлять объёмы перелива вверх до кратного 5: вместо 17 придётся налить 20"
                >
                  <input v-model="snapFive" type="checkbox" class="toggle toggle-primary toggle-sm" />
                  <span class="opacity-70">Перелив ×5</span>
                </label>
                <label class="flex cursor-pointer items-center gap-2 text-xs" title="Показать, из чего варить каждый ингредиент">
                  <input v-model="advancedMode" type="checkbox" class="toggle toggle-primary toggle-sm" />
                  <span class="opacity-70">Расширенный режим</span>
                </label>
                <label v-if="advancedMode" class="flex items-center gap-2 text-xs">
                  <span class="opacity-70">Глубина</span>
                  <select v-model.number="treeDepthLimit" class="select select-sm select-bordered w-20">
                    <option :value="1">1</option>
                    <option :value="2">2</option>
                    <option :value="3">3</option>
                    <option :value="4">4</option>
                    <option :value="5">5</option>
                    <option :value="6">6</option>
                    <option :value="7">7</option>
                    <option :value="8">8</option>
                    <option :value="9">9</option>
                  </select>
                </label>
                <button v-if="selectedId || groupFilter !== 'all'" class="btn btn-ghost btn-sm" @click="resetSelection">
                  Сбросить
                </button>
              </div>
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

              <div class="flex flex-col gap-1.5 sm:col-span-3">
                <span id="chem-reagent-label" class="text-xs font-medium uppercase tracking-wide opacity-60">
                  Реагент-продукт
                </span>
                <div ref="pickerRoot" class="relative">
                  <div
                    ref="pickerTrigger"
                    role="combobox"
                    tabindex="0"
                    aria-haspopup="listbox"
                    aria-controls="chem-reagent-listbox"
                    :aria-expanded="pickerOpen"
                    aria-labelledby="chem-reagent-label"
                    class="flex min-h-10 w-full cursor-pointer items-center justify-between gap-2 rounded-field border border-base-content/20 bg-base-100 px-3 text-sm transition-colors outline-none hover:border-base-content/40 focus-visible:border-base-content focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-base-content"
                    @click="togglePicker"
                    @keydown="onTriggerKeydown"
                  >
                    <span class="flex min-w-0 items-center gap-2">
                      <span
                        v-if="selectedReagent?.color"
                        class="size-2.5 shrink-0 rounded-full ring-1 ring-base-content/20"
                        :style="{ backgroundColor: selectedReagent.color }"
                      />
                      <span v-else class="size-2.5 shrink-0 rounded-full border border-dashed border-base-content/30" />
                      <span v-if="selectedId" class="truncate">
                        <span class="font-medium">{{ selectedName }}</span>
                        <span class="ml-2 text-xs opacity-60">{{ selectedNameEn }}</span>
                      </span>
                      <span v-else class="truncate opacity-50">Выберите реагент…</span>
                    </span>
                    <span class="flex shrink-0 items-center gap-1">
                      <button
                        v-if="selectedId"
                        type="button"
                        class="btn btn-ghost btn-xs btn-circle -mr-1.5"
                        aria-label="Сбросить выбранный реагент"
                        @click.stop="clearSelection"
                      >
                        <svg viewBox="0 0 16 16" fill="none" class="size-3.5" aria-hidden="true">
                          <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" />
                        </svg>
                      </button>
                      <svg
                        viewBox="0 0 16 16"
                        fill="none"
                        class="size-4 opacity-60 transition-transform"
                        :class="pickerOpen ? 'rotate-180' : ''"
                        aria-hidden="true"
                      >
                        <path d="M4 6.5L8 10.5L12 6.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" />
                      </svg>
                    </span>
                  </div>

                  <Transition
                    enter-active-class="transition duration-150 ease-out"
                    enter-from-class="scale-[0.985] -translate-y-1 opacity-0"
                    enter-to-class="scale-100 translate-y-0 opacity-100"
                    leave-active-class="transition duration-100 ease-in"
                    leave-from-class="scale-100 translate-y-0 opacity-100"
                    leave-to-class="scale-[0.985] -translate-y-1 opacity-0"
                  >
                    <div
                      v-if="pickerOpen"
                      class="absolute inset-x-0 top-full z-50 mt-1 origin-top overflow-hidden rounded-box border border-base-300 bg-base-100 shadow-xl"
                    >
                      <div class="p-2 pb-1.5">
                        <input
                          ref="pickerSearch"
                          v-model="pickerQuery"
                          type="text"
                          class="input input-sm w-full"
                          placeholder="Поиск: название (RU/EN) или id…"
                          autocomplete="off"
                          spellcheck="false"
                          aria-label="Поиск реагента"
                          aria-controls="chem-reagent-listbox"
                          :aria-activedescendant="activeOptionDomId || undefined"
                          @input="onSearchInput"
                          @keydown="onSearchKeydown"
                        />
                      </div>
                      <div
                        id="chem-reagent-listbox"
                        ref="pickerList"
                        role="listbox"
                        aria-labelledby="chem-reagent-label"
                        class="max-h-64 overflow-y-auto overscroll-contain pb-1"
                      >
                        <div v-for="entry in pickerGroups" :key="entry.group" role="group" :aria-label="entry.label">
                          <div
                            role="presentation"
                            class="sticky top-0 z-10 bg-base-100/95 px-3 py-1 text-[11px] font-semibold uppercase tracking-wide opacity-60 backdrop-blur-sm"
                          >
                            {{ entry.label }}
                          </div>
                          <div
                            v-for="option in entry.options"
                            :id="optionDomId(option.id)"
                            :key="option.id"
                            role="option"
                            :aria-selected="option.id === selectedId"
                            :data-active="activeOption?.id === option.id"
                            class="mx-1 flex cursor-pointer items-center gap-2 rounded-field px-2 py-1.5 text-sm"
                            :class="activeOption?.id === option.id ? 'bg-base-200' : 'hover:bg-base-200/60'"
                            @click="selectReagent(option.id)"
                            @mouseenter="setActive(option.id)"
                          >
                            <span
                              v-if="option.color"
                              class="size-2 shrink-0 rounded-full ring-1 ring-base-content/20"
                              :style="{ backgroundColor: option.color }"
                            />
                            <span v-else class="size-2 shrink-0 rounded-full border border-dashed border-base-content/30" />
                            <span class="min-w-0 flex-1 truncate">
                              <span class="font-medium">{{ option.ru }}</span>
                              <span class="ml-2 text-xs opacity-60">{{ option.en }}</span>
                            </span>
                            <svg
                              v-if="option.id === selectedId"
                              viewBox="0 0 16 16"
                              fill="none"
                              class="size-3.5 shrink-0 text-primary"
                              aria-hidden="true"
                            >
                              <path d="M3 8.5L6.5 12L13 5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
                            </svg>
                          </div>
                        </div>
                        <div v-if="pickerOptions.length === 0" class="px-3 py-5 text-center">
                          <p class="text-xs opacity-60">Ничего не найдено</p>
                          <p class="mt-1 text-[11px] opacity-40">Попробуйте другое название или id.</p>
                        </div>
                      </div>
                      <div class="hidden items-center gap-3 border-t border-base-300 px-3 py-1.5 text-[10px] opacity-50 sm:flex">
                        <span class="tabular-nums">{{ pickerOptions.length }} в списке</span>
                        <span class="ml-auto">↑ ↓ — выбор</span>
                        <span>Enter — подтвердить</span>
                        <span>Esc — закрыть</span>
                      </div>
                    </div>
                  </Transition>
                </div>
              </div>
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

              <!-- Карточка одного рецепта: сводка, предупреждения, таблица ингредиентов, дерево. -->
              <article
                v-for="(calc, index) in calculations"
                :key="calc.reaction.id"
                class="space-y-4 rounded-box border border-base-300 p-4"
              >
                <div class="flex flex-wrap items-center gap-2">
                  <h3 class="text-sm font-semibold">Рецепт {{ index + 1 }}</h3>
                  <span class="badge badge-ghost badge-sm">{{ groupLabel(calc.reaction.group) }}</span>
                  <span class="font-mono text-[11px] opacity-40">{{ calc.reaction.id }}</span>
                  <span v-if="calc.step > 1" class="badge badge-ghost badge-sm tabular-nums">×{{ calc.step }}</span>
                  <span class="badge badge-primary badge-soft badge-sm ml-auto">
                    выход {{ fmt(calc.yieldPerBatch) }} mL
                  </span>
                  <button
                    type="button"
                    class="btn btn-xs"
                    :class="isRecipeSaved(calc) ? 'btn-ghost' : 'btn-primary btn-soft'"
                    :disabled="isRecipeSaved(calc)"
                    :title="isRecipeSaved(calc)
                      ? 'Этот рецепт уже в правой панели'
                      : 'Добавить в сохранённые рецепты справа'"
                    @click="saveRecipe(calc)"
                  >
                    <svg viewBox="0 0 16 16" fill="none" class="size-3.5" aria-hidden="true">
                      <path
                        v-if="isRecipeSaved(calc)"
                        d="M3 8.5L6.5 12L13 5"
                        stroke="currentColor"
                        stroke-width="1.8"
                        stroke-linecap="round"
                        stroke-linejoin="round"
                      />
                      <path
                        v-else
                        d="M4 2.5h8v11L8 10.8 4 13.5v-11Z"
                        stroke="currentColor"
                        stroke-width="1.4"
                        stroke-linejoin="round"
                      />
                    </svg>
                    {{ isRecipeSaved(calc) ? 'Сохранено' : 'Сохранить' }}
                  </button>
                </div>

                <!-- Сводка: партии, объём партии, остаток в колбе и статус. -->
                <div class="stats stats-vertical w-full bg-base-200 sm:stats-horizontal">
                  <div class="stat">
                    <div class="stat-title text-xs">Партий</div>
                    <div class="stat-value text-2xl tabular-nums">{{ fmt(calc.batches, 0) }}</div>
                    <div class="stat-desc">минимум · получится {{ fmt(calc.produced) }} mL</div>
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

                <!-- Таблица: на реакцию — точная доля, «Перелить» — округлённый до шага объём. -->
                <div class="overflow-x-auto">
                  <table class="table table-zebra table-sm">
                    <thead>
                      <tr>
                        <th>Ингредиент</th>
                        <th class="text-right">На реакцию, mL</th>
                        <th class="text-right">Перелить, mL</th>
                        <th class="text-right">Доля объёма</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="ingredient in calc.ingredients" :key="ingredient.id" class="group">
                        <td>
                          <div class="flex items-center gap-2">
                            <span
                              v-if="ingredient.color"
                              class="size-2.5 shrink-0 rounded-full ring-1 ring-base-content/20"
                              :style="{ backgroundColor: ingredient.color }"
                              :title="ingredient.color"
                            />
                            <span v-else class="size-2.5 shrink-0 rounded-full border border-dashed border-base-content/30" />
                            <div class="min-w-0">
                              <div class="font-medium">{{ ingredient.name }} <span class="text-xs font-normal opacity-60">{{ ingredient.nameEn }}</span></div>
                              <div class="font-mono text-[10px] opacity-50">{{ ingredient.id }}</div>
                            </div>
                          </div>
                        </td>
                        <td class="text-right tabular-nums">{{ fmt(ingredient.perBatch) }}</td>
                        <td class="text-right font-semibold tabular-nums">
                          {{ fmt(ingredient.total) }}
                          <div v-if="ingredient.extra > 1e-9" class="text-[10px] font-normal opacity-50">
                            точно {{ fmt(ingredient.exactTotal) }}
                          </div>
                        </td>
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

                <p v-if="calc.pouredExtra > 1e-9" class="text-[11px] opacity-50">
                  Шаг перелива {{ calc.step }} mL: объёмы округлены вверх, запас
                  {{ fmt(calc.pouredExtra) }} mL останется в колбе неиспользованным.
                </p>

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

                <!-- Дерево подрецептов: из чего варить каждый ингредиент (только в расширенном режиме). -->
                <details
                  v-if="advancedMode && advancedTrees[calc.reaction.id]?.rows.length"
                  class="rounded-box border border-base-300 bg-base-200/40"
                  open
                >
                  <summary class="cursor-pointer select-none px-3 py-2 text-xs font-medium">
                    Подрецепты
                    <span class="ml-1 font-normal opacity-50">— из чего варить ингредиенты</span>
                  </summary>
                  <div class="space-y-0.5 px-2 pb-2">
                    <div
                      v-for="row in (advancedTrees[calc.reaction.id]?.rows ?? [])"
                      :key="row.key"
                      class="group flex flex-wrap items-center gap-x-2 gap-y-1 py-1 pr-1 text-xs"
                      :class="row.visualDepth > 0 ? 'border-l border-base-300 pl-2' : ''"
                      :style="{ marginLeft: `${row.visualDepth * 10}px` }"
                    >
                      <span
                        v-if="row.color"
                        class="size-2 shrink-0 rounded-full ring-1 ring-base-content/20"
                        :style="{ backgroundColor: row.color }"
                      />
                      <span v-else class="size-2 shrink-0 rounded-full border border-dashed border-base-content/30" />

                      <button
                        v-if="row.expandable"
                        type="button"
                        class="text-left underline decoration-base-content/30 decoration-dotted underline-offset-2 hover:decoration-base-content/70"
                        :aria-expanded="openTreeRows.has(row.key)"
                        @click="toggleTreeRow(row.key)"
                      >
                        {{ row.name }}
                      </button>
                      <span v-else class="font-medium" :class="row.kind === 'variant' ? 'opacity-60' : ''">
                        {{ row.name }}
                      </span>

                      <template v-if="row.kind === 'variant'">
                        <span class="badge badge-ghost badge-xs">{{ groupLabel(row.group) }}</span>
                        <span class="text-[11px] tabular-nums opacity-50">выход {{ fmt(row.amount) }} mL</span>
                        <span
                          v-for="label in row.requirements"
                          :key="label"
                          class="badge badge-warning badge-soft badge-xs"
                        >
                          {{ label }}
                        </span>
                        <span v-if="!row.requirements.length" class="badge badge-ghost badge-xs">без условий</span>
                      </template>
                      <template v-else>
                        <span class="tabular-nums opacity-70">{{ fmt(row.amount) }} mL</span>


                      </template>

                      <span
                        v-if="row.batches > 1"
                        class="badge badge-ghost badge-xs tabular-nums"
                        :title="`нужно ${fmt(row.batches, 0)} ${plural(row.batches, 'партия', 'партии', 'партий')} этого рецепта`"
                      >
                        ×{{ fmt(row.batches, 0) }}
                      </span>

                      <span v-if="row.cycle" class="badge badge-warning badge-soft badge-xs">цикл</span>
                      <span
                        v-else-if="row.tooDeep"
                        class="badge badge-ghost badge-xs"
                        :title="`рецепт раскрыт не глубже ${treeDepthLimit} уровней`"
                      >
                        глубина
                      </span>

                      <div
                        v-if="row.expandable && openTreeRows.has(row.key)"
                        class="w-full pl-4 text-[11px] opacity-70"
                      >
                        <span v-for="label in row.requirements" :key="label" class="badge badge-warning badge-soft badge-xs">
                          {{ label }}
                        </span>
                        <span class="ml-1 opacity-60">· {{ groupLabel(row.group) }}</span>
                      </div>
                    </div>

                    <p v-if="advancedTrees[calc.reaction.id]?.truncated" class="px-2 pt-1 text-[11px] opacity-50">
                      Дерево обрезано — показаны первые {{ MAX_TREE_ROWS }} строк.
                    </p>
                  </div>
                </details>
              </article>
            </template>
          </div>
        </div>

      </section>

      <aside class="space-y-3 xl:sticky xl:top-4">
        <div class="card bg-base-100 shadow-xl">
          <div class="card-body gap-3">
            <div class="flex items-center justify-between gap-2">
              <h2 class="card-title text-base">Сохранённые рецепты</h2>
              <span class="badge badge-ghost badge-sm tabular-nums">{{ savedRecipes.length }}</span>
            </div>

            <template v-if="savedEntries.length">
              <div class="flex flex-wrap items-center gap-2 text-xs">
                <label class="flex items-center gap-1.5">
                  <span class="opacity-60">Глубина</span>
                  <select v-model.number="savedDepthLimit" class="select select-xs select-bordered">
                    <option v-for="n in 6" :key="n" :value="n">{{ n }}</option>
                  </select>
                </label>
                <button type="button" class="btn btn-ghost btn-xs ml-auto" @click="clearSaved">Очистить</button>
              </div>

              <div class="space-y-2">
                <div v-for="entry in savedEntries" :key="entry.saved.key" class="rounded-box border border-base-300">
                  <div class="flex items-center gap-1 p-2">
                    <button
                      type="button"
                      class="btn btn-ghost btn-xs btn-square shrink-0"
                      :aria-expanded="savedOpen.has(entry.saved.key)"
                      :title="savedOpen.has(entry.saved.key) ? 'Свернуть рецепт' : 'Развернуть рецепт'"
                      @click="toggleSavedOpen(entry.saved.key)"
                    >
                      <svg
                        viewBox="0 0 16 16"
                        fill="none"
                        class="size-3 transition-transform"
                        :class="savedOpen.has(entry.saved.key) ? 'rotate-180' : ''"
                        aria-hidden="true"
                      >
                        <path d="M4 6.5L8 10.5L12 6.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" />
                      </svg>
                    </button>

                    <div class="min-w-0 flex-1">
                      <button
                        type="button"
                        class="block w-full min-w-0 text-left"
                        title="Загрузить рецепт в калькулятор"
                        @click="loadSaved(entry.saved)"
                      >
                        <span class="flex min-w-0 items-center gap-1.5">
                          <span
                            v-if="reagentById.get(entry.saved.reagentId)?.color"
                            class="size-2 shrink-0 rounded-full ring-1 ring-base-content/20"
                            :style="{ backgroundColor: reagentById.get(entry.saved.reagentId)?.color ?? undefined }"
                          />
                          <span v-else class="size-2 shrink-0 rounded-full border border-dashed border-base-content/30" />
                          <span class="truncate text-sm font-medium">{{ savedReagentName(entry.saved.reagentId) }}</span>
                        </span>
                      </button>
                      <div class="mt-0.5 flex flex-wrap items-center gap-x-1 gap-y-0.5 text-[11px] tabular-nums">
                        <label class="flex items-center gap-1 opacity-70">
                          <span class="sr-only">Целевой объём {{ savedReagentName(entry.saved.reagentId) }}</span>
                          <input
                            :value="entry.saved.target"
                            type="number"
                            min="0.1"
                            step="0.1"
                            inputmode="decimal"
                            class="input input-xs w-[4.5rem] px-1.5 tabular-nums"
                            title="Целевой объём, mL"
                            @change="updateSavedTarget(entry.saved.key, $event)"
                          />
                          <span>mL</span>
                        </label>
                        <span class="opacity-50">· {{ fmt(entry.calc.batches, 0) }} {{ plural(entry.calc.batches, 'партия', 'партии', 'партий') }}</span>
                      </div>
                    </div>

                    <button
                      type="button"
                      class="btn btn-ghost btn-xs btn-square shrink-0"
                      title="Удалить из сохранённых"
                      @click="removeSaved(entry.saved.key)"
                    >
                      <svg viewBox="0 0 16 16" fill="none" class="size-3.5" aria-hidden="true">
                        <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" />
                      </svg>
                    </button>
                  </div>

                  <div v-if="savedOpen.has(entry.saved.key)" class="space-y-1 border-t border-base-300 px-2 py-2">
                    <p class="text-[11px] opacity-50">
                      получится {{ fmt(entry.calc.produced) }} mL · {{ groupLabel(entry.calc.reaction.group) }}
                    </p>

                    <div v-if="entry.tree.rows.length" class="space-y-0.5">
                      <div
                        v-for="row in visibleSavedRows(entry.tree)"
                        :key="row.key"
                        class="flex flex-wrap items-center gap-x-1.5 gap-y-0.5 py-0.5 text-[11px]"
                        :style="{ marginLeft: `${row.visualDepth * 10}px` }"
                        :title="row.kind === 'variant' && row.requirements.length ? row.requirements.join(' · ') : undefined"
                      >
                        <button
                          v-if="savedRowHasChildren(entry.tree.rows, row.key)"
                          type="button"
                          class="btn btn-ghost btn-xs btn-square size-5 min-h-0 shrink-0 p-0"
                          :aria-expanded="!isSavedRowCollapsed(row, entry.tree.rows)"
                          :title="isSavedRowCollapsed(row, entry.tree.rows) ? 'Развернуть подрецепт' : 'Свернуть подрецепт'"
                          @click="toggleSavedRow(row, entry.tree.rows)"
                        >
                          <svg
                            viewBox="0 0 16 16"
                            fill="none"
                            class="size-3 transition-transform"
                            :class="isSavedRowCollapsed(row, entry.tree.rows) ? '-rotate-90' : ''"
                            aria-hidden="true"
                          >
                            <path d="M4 6.5L8 10.5L12 6.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" />
                          </svg>
                        </button>
                        <span v-else class="size-5 shrink-0" />

                        <span
                          v-if="row.color"
                          class="size-2 shrink-0 rounded-full ring-1 ring-base-content/20"
                          :style="{ backgroundColor: row.color }"
                        />
                        <span v-else class="size-2 shrink-0 rounded-full border border-dashed border-base-content/30" />

                        <span class="font-medium" :class="row.kind === 'variant' ? 'opacity-60' : ''">{{ row.name }}</span>
                        <span class="tabular-nums opacity-60">{{ fmt(row.amount) }}</span>
                        <span v-if="row.kind === 'variant'" class="badge badge-ghost badge-xs">{{ groupLabel(row.group) }}</span>
                        <span
                          v-if="row.batches > 1"
                          class="badge badge-ghost badge-xs tabular-nums"
                          :title="`нужно ${fmt(row.batches, 0)} ${plural(row.batches, 'партия', 'партии', 'партий')} этого рецепта`"
                        >
                          ×{{ fmt(row.batches, 0) }}
                        </span>
                        <span v-if="row.cycle" class="badge badge-warning badge-soft badge-xs">цикл</span>
                        <span
                          v-else-if="row.tooDeep"
                          class="badge badge-ghost badge-xs"
                          :title="`рецепт раскрыт не глубже ${savedDepthLimit} уровней`"
                        >
                          глубина
                        </span>
                      </div>
                    </div>
                    <p v-else class="text-[11px] opacity-50">Все ингредиенты — готовые реагенты.</p>
                    <p v-if="entry.tree.truncated" class="text-[11px] opacity-50">Дерево обрезано.</p>
                  </div>
                </div>
              </div>
            </template>

            <p v-else class="text-xs opacity-60">
              Нажмите «Сохранить» у рецепта — он появится здесь и останется после перезагрузки.
            </p>
          </div>
        </div>
      </aside>
    </div>
  </div>
</template>
