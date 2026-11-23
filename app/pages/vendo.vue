<script setup lang="ts">
import vendoData from '~/data/vendo.json'

type CatalogItem = {
  id: string
  name: string
  nameEn: string
  price: number
}

type ShuttleItem = {
  id: string
  count: number
}

type Shuttle = {
  id: string
  name: string
  price: number
  appraisal: number
  category: string
  group: string
  classes: string[]
  engines: string[]
  shuttlePath: string
  purchasable: boolean
  items: ShuttleItem[]
}

type CartEntry = {
  id: string
  qty: number
}

const SELL_RATE = typeof vendoData.sellRate === 'number' ? vendoData.sellRate : 0.85
const catalog = vendoData.catalog as CatalogItem[]
const shuttles = (vendoData.shuttles as Shuttle[]).filter(s => s.purchasable && s.price > 0)

const catalogById = new Map(catalog.map(item => [item.id, item]))
const shuttleItemMaps = new Map(shuttles.map(s => [s.id, new Map(s.items.map(i => [i.id, i.count]))]))

const cart = ref<CartEntry[]>([])
const partQuery = ref('')
const shuttleQuery = ref('')
const selectedGroups = ref<string[]>([])
const showOnlyMatches = ref(true)
const sortMode = ref<'smart' | 'net' | 'buy' | 'coverage'>('smart')

const CART_KEY = 'vendo:cart'

function fmt(n: number): string {
  return Math.round(n).toLocaleString('ru-RU')
}

function sellReturn(appraisal: number): number {
  return Math.floor(Math.max(0, appraisal) * SELL_RATE)
}

function cartQty(id: string): number {
  return cart.value.find(e => e.id === id)?.qty ?? 0
}

function addToCart(id: string) {
  if (!catalogById.has(id)) return
  const existing = cart.value.find(e => e.id === id)
  if (existing) existing.qty += 1
  else cart.value.push({ id, qty: 1 })
}

function removeFromCart(id: string) {
  cart.value = cart.value.filter(e => e.id !== id)
}

function setCartQty(id: string, qty: number) {
  const entry = cart.value.find(e => e.id === id)
  if (!entry) return
  const v = Math.floor(Number(qty))
  if (!Number.isFinite(v) || v <= 0) {
    removeFromCart(id)
    return
  }
  entry.qty = v
}

function clearCart() {
  cart.value = []
}

const partSearchResults = computed(() => {
  const q = partQuery.value.trim().toLowerCase()
  const base = q
    ? catalog.filter(item => {
        const hay = `${item.name} ${item.nameEn} ${item.id}`.toLowerCase()
        return hay.includes(q)
      })
    : catalog
  return base.slice(0, 40)
})

const groups = computed(() => {
  const set = new Set<string>()
  for (const s of shuttles) set.add(s.group || 'Unknown')
  return [...set].sort()
})

function groupLabel(g: string): string {
  return g || 'Unknown'
}

function toggleGroup(g: string) {
  const idx = selectedGroups.value.indexOf(g)
  if (idx >= 0) selectedGroups.value = selectedGroups.value.filter(x => x !== g)
  else selectedGroups.value = [...selectedGroups.value, g]
}

function clearGroups() {
  selectedGroups.value = []
}

type ShuttleRow = {
  shuttle: Shuttle
  baseReturn: number
  removedValue: number
  sellAfter: number
  netCost: number
  matched: Array<{ id: string; name: string; want: number; have: number; take: number; unitPrice: number; totalPrice: number }>
  matchedCount: number
  wantedCount: number
  coverage: number
  score: number
}

const shuttleRows = computed<ShuttleRow[]>(() => {
  const wanted = cart.value.filter(e => e.qty > 0 && catalogById.has(e.id))
  const wantedCount = wanted.reduce((a, e) => a + e.qty, 0)
  const q = shuttleQuery.value.trim().toLowerCase()

  const rows: ShuttleRow[] = []
  const groupSet = selectedGroups.value.length > 0 ? new Set(selectedGroups.value) : null
  for (const shuttle of shuttles) {
    const g = shuttle.group || 'Unknown'
    if (groupSet && !groupSet.has(g)) continue
    if (q) {
      const hay = `${shuttle.name} ${shuttle.id} ${shuttle.group} ${shuttle.classes.join(' ')}`.toLowerCase()
      if (!hay.includes(q)) continue
    }

    const itemMap = shuttleItemMaps.get(shuttle.id)
    const matched: ShuttleRow['matched'] = []
    let removedValue = 0
    let matchedCount = 0

    for (const entry of wanted) {
      const have = itemMap?.get(entry.id) ?? 0
      if (have <= 0) continue
      const take = Math.min(have, entry.qty)
      const cat = catalogById.get(entry.id)
      const unitPrice = cat?.price ?? 0
      const totalPrice = unitPrice * take
      removedValue += totalPrice
      matchedCount += take
      matched.push({
        id: entry.id,
        name: cat?.name ?? entry.id,
        want: entry.qty,
        have,
        take,
        unitPrice,
        totalPrice,
      })
    }

    if (showOnlyMatches.value && wanted.length > 0 && matched.length === 0) continue

    const baseReturn = sellReturn(shuttle.appraisal)
    const sellAfter = sellReturn(shuttle.appraisal - removedValue)
    const netCost = shuttle.price - sellAfter
    const coverage = wantedCount > 0 ? matchedCount / wantedCount : 0
    const coveragePenalty = wantedCount > 0 ? (1 - coverage) * 1_000_000 : 0
    const score = coveragePenalty + netCost

    rows.push({
      shuttle,
      baseReturn,
      removedValue,
      sellAfter,
      netCost,
      matched,
      matchedCount,
      wantedCount,
      coverage,
      score,
    })
  }

  rows.sort((a, b) => {
    if (sortMode.value === 'net') return a.netCost - b.netCost || b.coverage - a.coverage
    if (sortMode.value === 'buy') return a.shuttle.price - b.shuttle.price || b.coverage - a.coverage
    if (sortMode.value === 'coverage') return b.coverage - a.coverage || a.netCost - b.netCost
    return a.score - b.score || b.matchedCount - a.matchedCount || a.shuttle.price - b.shuttle.price
  })

  return rows
})

const summary = computed(() => {
  const wanted = cart.value.filter(e => e.qty > 0)
  const wantedCount = wanted.reduce((a, e) => a + e.qty, 0)
  const best = shuttleRows.value[0]
  return {
    wantedKinds: wanted.length,
    wantedCount,
    best,
    shuttleCount: shuttleRows.value.length,
  }
})

const smartPlan = computed(() => {
  const wanted = new Map<string, number>()
  for (const e of cart.value) {
    if (e.qty > 0 && catalogById.has(e.id)) wanted.set(e.id, e.qty)
  }
  if (wanted.size === 0) return { picks: [] as Array<{ shuttle: Shuttle; take: Array<{ id: string; name: string; qty: number; unitPrice: number }>; netCost: number; sellAfter: number; removedValue: number }>, remaining: [] as Array<{ id: string; name: string; qty: number }>, totalNet: 0 }

  const remaining = new Map(wanted)
  const picks: Array<{ shuttle: Shuttle; take: Array<{ id: string; name: string; qty: number; unitPrice: number }>; netCost: number; sellAfter: number; removedValue: number }> = []
  const usedShuttles = new Set<string>()

  for (let step = 0; step < 8; step++) {
    let best: { shuttle: Shuttle; take: Array<{ id: string; name: string; qty: number; unitPrice: number }>; netCost: number; sellAfter: number; removedValue: number; gain: number } | null = null

    for (const shuttle of shuttles) {
      if (usedShuttles.has(shuttle.id)) continue
      const itemMap = shuttleItemMaps.get(shuttle.id)
      if (!itemMap) continue
      const take: Array<{ id: string; name: string; qty: number; unitPrice: number }> = []
      let removedValue = 0
      let gain = 0
      for (const [id, need] of remaining) {
        const have = itemMap.get(id) ?? 0
        if (have <= 0) continue
        const qty = Math.min(have, need)
        const cat = catalogById.get(id)
        const unitPrice = cat?.price ?? 0
        take.push({ id, name: cat?.name ?? id, qty, unitPrice })
        removedValue += unitPrice * qty
        gain += qty
      }
      if (gain <= 0) continue
      const sellAfter = sellReturn(shuttle.appraisal - removedValue)
      const netCost = shuttle.price - sellAfter
      if (!best) {
        best = { shuttle, take, netCost, sellAfter, removedValue, gain }
        continue
      }
      const bestRatio = best.netCost / best.gain
      const ratio = netCost / gain
      if (ratio < bestRatio - 1e-9 || (Math.abs(ratio - bestRatio) < 1e-9 && (gain > best.gain || (gain === best.gain && netCost < best.netCost)))) {
        best = { shuttle, take, netCost, sellAfter, removedValue, gain }
      }
    }

    if (!best) break
    picks.push({ shuttle: best.shuttle, take: best.take, netCost: best.netCost, sellAfter: best.sellAfter, removedValue: best.removedValue })
    usedShuttles.add(best.shuttle.id)
    for (const t of best.take) {
      const left = (remaining.get(t.id) ?? 0) - t.qty
      if (left <= 0) remaining.delete(t.id)
      else remaining.set(t.id, left)
    }
    if (remaining.size === 0) break
  }

  const remainingList = [...remaining.entries()].map(([id, qty]) => ({ id, name: catalogById.get(id)?.name ?? id, qty }))
  const totalNet = picks.reduce((a, p) => a + p.netCost, 0)
  return { picks, remaining: remainingList, totalNet }
})

onMounted(() => {
  if (!import.meta.client) return
  try {
    const raw = localStorage.getItem(CART_KEY)
    if (!raw) return
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return
    cart.value = parsed.filter((x): x is CartEntry => (
      x && typeof x.id === 'string' && typeof x.qty === 'number' && x.qty > 0 && catalogById.has(x.id)
    )).map(x => ({ id: x.id, qty: Math.floor(x.qty) }))
  } catch { /* ignore */ }
})

watch(cart, (val) => {
  if (!import.meta.client) return
  try { localStorage.setItem(CART_KEY, JSON.stringify(val)) } catch { /* ignore */ }
}, { deep: true })
</script>

<template>
  <div class="space-y-4">
    <header class="flex flex-wrap items-end gap-3 px-1">
      <div>
        <h1 class="text-xl font-bold leading-tight">Vendo / Скручивание</h1>
        <p class="text-xs opacity-60">Корзина деталей: покупаешь шаттл, скручиваешь нужное, продаёшь шаттл. Считаем возврат и подбираем шаттлы с минимальными затратами.</p>
      </div>
      <p class="ml-auto text-[11px] tabular-nums opacity-50">{{ shuttles.length }} шаттлов · {{ catalog.length }} деталей · возврат {{ Math.round(SELL_RATE * 100) }}%</p>
    </header>

    <div class="grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_24rem]">
      <section class="min-w-0 space-y-4">
        <div class="card bg-base-100 shadow-xl">
          <div class="card-body gap-4">
            <div class="flex flex-wrap items-center gap-2">
              <h2 class="card-title text-base">Подбор шаттлов</h2>
              <div class="ml-auto flex flex-wrap gap-2">
                <label class="input input-sm w-56">
                  <input v-model="shuttleQuery" type="search" placeholder="Поиск шаттла..." />
                </label>
                <details class="dropdown dropdown-end">
                  <summary class="btn btn-sm btn-outline m-0">
                    Консоли{{ selectedGroups.length ? ` (${selectedGroups.length})` : ': все' }}
                  </summary>
                  <div class="dropdown-content z-20 mt-1 w-64 rounded-box border border-base-300 bg-base-100 p-2 shadow-lg">
                    <div class="flex items-center justify-between px-1 pb-2">
                      <span class="text-xs opacity-60">Фильтр по консолям</span>
                      <button v-if="selectedGroups.length" class="btn btn-ghost btn-xs" @click.prevent="clearGroups">Сбросить</button>
                    </div>
                    <div class="max-h-64 overflow-auto space-y-1">
                      <label v-for="g in groups" :key="g" class="flex cursor-pointer items-center gap-2 rounded px-1 py-1 hover:bg-base-200 text-sm">
                        <input type="checkbox" class="checkbox checkbox-sm" :checked="selectedGroups.includes(g)" @change="toggleGroup(g)" />
                        <span class="truncate">{{ g }}</span>
                      </label>
                    </div>
                  </div>
                </details>
                <select v-model="sortMode" class="select select-sm select-bordered">
                  <option value="smart">Умный подбор</option>
                  <option value="net">Мин. чистые затраты</option>
                  <option value="coverage">Макс. покрытие</option>
                  <option value="buy">Мин. цена покупки</option>
                </select>
              </div>
            </div>

            <label class="flex cursor-pointer items-center gap-2 text-xs">
              <input v-model="showOnlyMatches" type="checkbox" class="toggle toggle-sm toggle-primary" />
              <span class="opacity-70">Показывать только шаттлы, где есть детали из корзины</span>
            </label>

            <div class="stats stats-vertical sm:stats-horizontal bg-base-200 shadow-sm">
              <div class="stat py-3">
                <div class="stat-title text-xs">В корзине</div>
                <div class="stat-value text-lg tabular-nums">{{ summary.wantedKinds }}</div>
                <div class="stat-desc">{{ summary.wantedCount }} шт. всего</div>
              </div>
              <div class="stat py-3">
                <div class="stat-title text-xs">Подходящих шаттлов</div>
                <div class="stat-value text-lg tabular-nums">{{ summary.shuttleCount }}</div>
                <div class="stat-desc">из {{ shuttles.length }}</div>
              </div>
              <div class="stat py-3">
                <div class="stat-title text-xs">Лучший вариант</div>
                <div class="stat-value text-lg truncate">{{ summary.best?.shuttle.name ?? '—' }}</div>
                <div class="stat-desc tabular-nums" v-if="summary.best">чистые затраты {{ fmt(summary.best.netCost) }}</div>
              </div>
            </div>

            <div v-if="cart.length > 0" class="rounded-box border border-base-300 p-3 space-y-2">
              <div class="flex flex-wrap items-center gap-2">
                <h3 class="font-semibold text-sm">Умный план</h3>
                <span class="text-xs opacity-60">жадный подбор по минимальным затратам на нужную деталь</span>
                <span class="ml-auto text-xs tabular-nums" v-if="smartPlan.picks.length">Итого чистые затраты: <b>{{ fmt(smartPlan.totalNet) }}</b></span>
              </div>
              <div v-if="smartPlan.picks.length === 0" class="text-xs opacity-60">Нет шаттлов, покрывающих корзину.</div>
              <div v-else class="space-y-2">
                <div v-for="(pick, idx) in smartPlan.picks" :key="pick.shuttle.id" class="flex flex-wrap items-start gap-2 text-sm border-t border-base-300 pt-2 first:border-t-0 first:pt-0">
                  <span class="badge badge-primary badge-sm">{{ idx + 1 }}</span>
                  <div class="min-w-0 flex-1">
                    <div class="font-medium">{{ pick.shuttle.name }} <span class="opacity-50 text-xs">({{ pick.shuttle.id }})</span></div>
                    <div class="text-xs opacity-70">
                      Покупка {{ fmt(pick.shuttle.price) }} · возврат после скрутки {{ fmt(pick.sellAfter) }} · <span class="font-semibold">чистые {{ fmt(pick.netCost) }}</span>
                    </div>
                    <div class="flex flex-wrap gap-1 mt-1">
                      <span v-for="t in pick.take" :key="t.id" class="badge badge-ghost badge-sm">
                        {{ t.name }} ×{{ t.qty }}
                      </span>
                    </div>
                  </div>
                </div>
                <div v-if="smartPlan.remaining.length" class="alert alert-warning py-2 text-xs">
                  <span>Не найдено на покупных шаттлах: {{ smartPlan.remaining.map(r => `${r.name} ×${r.qty}`).join(', ') }}</span>
                </div>
              </div>
            </div>

            <div class="overflow-x-auto">
              <table class="table table-sm">
                <thead>
                  <tr>
                    <th>Шаттл</th>
                    <th class="text-right">Покупка</th>
                    <th class="text-right">Возврат {{ Math.round(SELL_RATE * 100) }}%</th>
                    <th class="text-right">После скрутки</th>
                    <th class="text-right">Потеря</th>
                    <th class="text-right">Чистые</th>
                    <th>Детали из корзины</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="row in shuttleRows.slice(0, 80)" :key="row.shuttle.id" :class="row.matched.length ? '' : 'opacity-60'">
                    <td>
                      <div class="font-medium">{{ row.shuttle.name }}</div>
                      <div class="text-[11px] opacity-50">{{ row.shuttle.group }} · {{ row.shuttle.category }} · {{ row.shuttle.id }}</div>
                    </td>
                    <td class="text-right tabular-nums">{{ fmt(row.shuttle.price) }}</td>
                    <td class="text-right tabular-nums">{{ fmt(row.baseReturn) }}</td>
                    <td class="text-right tabular-nums">{{ fmt(row.sellAfter) }}</td>
                    <td class="text-right tabular-nums text-warning">{{ row.removedValue ? fmt(row.baseReturn - row.sellAfter) : '—' }}</td>
                    <td class="text-right tabular-nums font-semibold">{{ fmt(row.netCost) }}</td>
                    <td>
                      <div v-if="row.matched.length" class="flex flex-wrap gap-1">
                        <span v-for="m in row.matched" :key="m.id" class="badge badge-outline badge-sm" :title="`${m.name}: есть ${m.have}, нужно ${m.want}, берём ${m.take}, цена ${fmt(m.unitPrice)}`">
                          {{ m.name }} {{ m.take }}/{{ m.want }}
                        </span>
                      </div>
                      <span v-else class="text-xs opacity-40">—</span>
                    </td>
                  </tr>
                  <tr v-if="shuttleRows.length === 0">
                    <td colspan="7" class="text-center py-8 opacity-60">Нет подходящих шаттлов. Добавьте детали в корзину или измените фильтры.</td>
                  </tr>
                </tbody>
              </table>
              <p v-if="shuttleRows.length > 80" class="text-xs opacity-50 mt-2 px-1">Показаны первые 80 из {{ shuttleRows.length }}.</p>
            </div>

            <p class="text-[11px] opacity-50">
              Возврат считается как <code>floor(оценка_шаттла × {{ SELL_RATE }})</code> — как в игре (базовая ставка верфи, без налогов консоли). Оценка считается по игровой формуле PricingSystem (StaticPrice/Material/Stack/Solution), для машин без прямой цены — по составу платы (MachineBoard). «Чистые затраты» = покупка − возврат после скрутки.
            </p>
          </div>
        </div>
      </section>

      <aside class="space-y-4 xl:sticky xl:top-4">
        <div class="card bg-base-100 shadow-xl">
          <div class="card-body gap-3">
            <div class="flex items-center gap-2">
              <h2 class="card-title text-base">Корзина деталей</h2>
              <button v-if="cart.length" class="btn btn-ghost btn-xs ml-auto" @click="clearCart">Очистить</button>
            </div>

            <label class="input input-sm w-full">
              <input v-model="partQuery" type="search" placeholder="Добавить деталь: ИнжеМат, протолат, щит..." />
            </label>

            <div class="max-h-56 overflow-auto rounded-box border border-base-300" v-if="partQuery.trim() || cart.length === 0">
              <button
                v-for="item in partSearchResults"
                :key="item.id"
                class="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-base-200 text-sm border-b border-base-300 last:border-b-0"
                @click="addToCart(item.id)"
              >
                <span class="min-w-0 flex-1">
                  <span class="font-medium block truncate">{{ item.name }}</span>
                  <span class="text-[11px] opacity-50 block truncate">{{ item.nameEn }} · {{ item.id }}</span>
                </span>
                <span class="text-xs tabular-nums opacity-60">{{ fmt(item.price) }}</span>
                <span class="btn btn-primary btn-xs">+</span>
              </button>
              <div v-if="partSearchResults.length === 0" class="px-3 py-4 text-xs opacity-60 text-center">Ничего не найдено</div>
            </div>

            <div v-if="cart.length" class="space-y-2">
              <div v-for="entry in cart" :key="entry.id" class="rounded-box border border-base-300 p-2">
                <div class="flex items-start gap-2">
                  <div class="min-w-0 flex-1">
                    <div class="font-medium text-sm leading-tight">{{ catalogById.get(entry.id)?.name ?? entry.id }}</div>
                    <div class="text-[11px] opacity-50 truncate">{{ catalogById.get(entry.id)?.nameEn }} · {{ fmt(catalogById.get(entry.id)?.price ?? 0) }} за шт.</div>
                  </div>
                  <button class="btn btn-ghost btn-xs" @click="removeFromCart(entry.id)">✕</button>
                </div>
                <div class="mt-2 flex items-center gap-2">
                  <span class="text-xs opacity-60">Кол-во</span>
                  <input
                    :value="entry.qty"
                    type="number"
                    min="1"
                    step="1"
                    class="input input-xs input-bordered w-20 tabular-nums"
                    @change="(e) => setCartQty(entry.id, Number((e.target as HTMLInputElement).value))"
                  />
                  <span class="text-xs opacity-50 tabular-nums ml-auto">= {{ fmt((catalogById.get(entry.id)?.price ?? 0) * entry.qty) }}</span>
                </div>
              </div>
            </div>
            <p v-else class="text-xs opacity-60">Добавьте детали, которые хотите скрутить. Например: ИнжеМат, протолат, генератор щита.</p>
          </div>
        </div>
      </aside>
    </div>
  </div>
</template>
