import { Search } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import clsx from 'clsx'

type BadgeKind = 'hot' | 'cold' | 'waiting' | 'info'

type CellItem = {
  kind: BadgeKind
  label: string
}

type CellValue = CellItem[] | null | 'x'

type Exchange = {
  id: string
  name: string
  count: number
}

type AssetRow = {
  asset: string
  cells: Record<string, CellValue>
}

function useTheme() {
  const [theme, setTheme] = useState<'dark' | 'light'>(() => {
    const fromStorage = localStorage.getItem('theme')
    if (fromStorage === 'light' || fromStorage === 'dark') return fromStorage
    return window.matchMedia?.('(prefers-color-scheme: dark)')?.matches ? 'dark' : 'dark'
  })

  useEffect(() => {
    const root = document.documentElement
    root.classList.toggle('dark', theme === 'dark')
    root.classList.toggle('light', theme === 'light')
    localStorage.setItem('theme', theme)
  }, [theme])

  return { theme, setTheme }
}

function Badge({ kind, label }: CellItem) {
  const palette = (() => {
    switch (kind) {
      case 'hot':
        return { dot: 'bg-emerald-400', bg: 'bg-white/5', text: 'text-slate-100' }
      case 'cold':
        return { dot: 'bg-amber-400', bg: 'bg-white/5', text: 'text-slate-100' }
      case 'waiting':
        return { dot: 'bg-amber-300', bg: 'bg-amber-300/10', text: 'text-amber-200' }
      case 'info':
        return { dot: 'bg-sky-400', bg: 'bg-sky-400/10', text: 'text-sky-200' }
    }
  })()

  return (
    <span
      className={clsx(
        'inline-flex items-center gap-2 rounded-full border border-white/10 px-3 py-1 text-xs font-semibold',
        palette.bg,
        palette.text,
      )}
    >
      <span className={clsx('h-2 w-2 rounded-full', palette.dot)} />
      <span>{label}</span>
    </span>
  )
}

function CheckPill({
  checked,
  onChange,
  label,
}: {
  checked: boolean
  onChange: (checked: boolean) => void
  label: string
}) {
  return (
    <label className="inline-flex cursor-pointer select-none items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="h-4 w-4 accent-sky-500"
      />
      <span className="text-slate-100">{label}</span>
    </label>
  )
}

function TogglePill({
  checked,
  onChange,
  label,
}: {
  checked: boolean
  onChange: (checked: boolean) => void
  label: string
}) {
  return (
    <label className="inline-flex cursor-pointer select-none items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="h-4 w-4 accent-sky-500"
      />
      <span className="text-slate-100">{label}</span>
    </label>
  )
}

function isConnected(cell: CellValue) {
  return Array.isArray(cell) && cell.length > 0
}

export default function App() {
  const { theme, setTheme } = useTheme()

  const exchanges: Exchange[] = useMemo(
    () => [
      { id: 'btcturk', name: 'BtcTürk', count: 91 },
      { id: 'paribu', name: 'Paribu', count: 86 },
      { id: 'binance', name: 'Binance', count: 5 },
      { id: 'okx', name: 'Okx', count: 3 },
      { id: 'bybit', name: 'Bybit', count: 3 },
      { id: 'gate', name: 'Gate', count: 4 },
      { id: 'mexc', name: 'Mexc', count: 4 },
      { id: 'bitget', name: 'Bitget', count: 2 },
      { id: 'kucoin', name: 'KuCoin', count: 1 },
      { id: 'coinbase', name: 'Coinbase', count: 2 },
    ],
    [],
  )

  const rows: AssetRow[] = useMemo(
    () => [
      {
        asset: 'CHZ',
        cells: {
          btcturk: [
            { kind: 'hot', label: 'HOT' },
            { kind: 'cold', label: 'COLD' },
          ],
          paribu: [
            { kind: 'hot', label: 'HOT' },
            { kind: 'cold', label: 'COLD' },
          ],
          binance: [{ kind: 'hot', label: 'HOT' }, { kind: 'cold', label: 'COLD' }],
          okx: [{ kind: 'hot', label: 'HOT' }],
          bybit: [{ kind: 'hot', label: 'HOT' }],
          gate: [{ kind: 'hot', label: 'HOT' }],
          mexc: [{ kind: 'hot', label: 'HOT' }],
          bitget: [{ kind: 'hot', label: 'HOT' }],
          kucoin: null,
          coinbase: null,
        },
      },
      {
        asset: 'ETH',
        cells: {
          btcturk: [
            { kind: 'hot', label: 'HOT' },
            { kind: 'cold', label: 'COLD' },
          ],
          paribu: [
            { kind: 'hot', label: 'HOT' },
            { kind: 'cold', label: 'COLD' },
          ],
          binance: [
            { kind: 'hot', label: 'HOT-14' },
            { kind: 'hot', label: 'HOT-15' },
            { kind: 'hot', label: 'HOT-16' },
          ],
          okx: [{ kind: 'hot', label: 'HOT' }],
          bybit: [{ kind: 'hot', label: 'HOT' }],
          gate: [{ kind: 'hot', label: 'HOT' }],
          mexc: [{ kind: 'hot', label: 'HOT' }],
          bitget: [{ kind: 'hot', label: 'HOT' }],
          kucoin: [{ kind: 'hot', label: 'HOT' }],
          coinbase: [{ kind: 'hot', label: 'HOT' }, { kind: 'waiting', label: 'Bekleniyor' }],
        },
      },
      {
        asset: 'SOL',
        cells: {
          btcturk: [
            { kind: 'hot', label: 'HOT' },
            { kind: 'cold', label: 'COLD' },
          ],
          paribu: [{ kind: 'hot', label: 'HOT' }, { kind: 'cold', label: 'COLD' }],
          binance: null,
          okx: null,
          bybit: null,
          gate: [{ kind: 'hot', label: 'HOT' }],
          mexc: [{ kind: 'hot', label: 'HOT' }],
          bitget: null,
          kucoin: null,
          coinbase: null,
        },
      },
      {
        asset: 'BSC',
        cells: {
          btcturk: 'x',
          paribu: [{ kind: 'hot', label: 'HOT' }, { kind: 'cold', label: 'COLD' }],
          binance: null,
          okx: null,
          bybit: null,
          gate: null,
          mexc: null,
          bitget: null,
          kucoin: null,
          coinbase: null,
        },
      },
      {
        asset: 'TRX',
        cells: {
          btcturk: [{ kind: 'hot', label: 'HOT' }, { kind: 'cold', label: 'COLD' }],
          paribu: [{ kind: 'hot', label: 'HOT' }, { kind: 'waiting', label: 'Bekleniyor' }],
          binance: null,
          okx: null,
          bybit: null,
          gate: null,
          mexc: null,
          bitget: null,
          kucoin: null,
          coinbase: null,
        },
      },
      {
        asset: 'AVAX',
        cells: {
          btcturk: [{ kind: 'hot', label: 'HOT' }, { kind: 'cold', label: 'COLD' }],
          paribu: [{ kind: 'hot', label: 'HOT' }, { kind: 'cold', label: 'COLD' }],
          binance: null,
          okx: null,
          bybit: null,
          gate: null,
          mexc: null,
          bitget: null,
          kucoin: null,
          coinbase: null,
        },
      },
    ],
    [],
  )

  const [query, setQuery] = useState('')
  const [hideEmptyColumns, setHideEmptyColumns] = useState(false)
  const [hideDisconnectedRows, setHideDisconnectedRows] = useState(false)

  const [visibleExchangeIds, setVisibleExchangeIds] = useState<string[]>(
    () => exchanges.map((e) => e.id),
  )

  const filteredRows = useMemo(() => {
    const q = query.trim().toLowerCase()
    const byQuery = (r: AssetRow) => {
      if (!q) return true
      if (r.asset.toLowerCase().includes(q)) return true
      // badge etiketlerinde ara (örn HOT, COLD, Bekleniyor)
      return Object.values(r.cells).some((cell) => {
        if (!Array.isArray(cell)) return false
        return cell.some((b) => b.label.toLowerCase().includes(q))
      })
    }

    const byConnection = (r: AssetRow) => {
      if (!hideDisconnectedRows) return true
      return visibleExchangeIds.some((id) => isConnected(r.cells[id] ?? null))
    }

    return rows.filter((r) => byQuery(r) && byConnection(r))
  }, [query, hideDisconnectedRows, rows, visibleExchangeIds])

  const effectiveExchangeIds = useMemo(() => {
    const base = exchanges.filter((e) => visibleExchangeIds.includes(e.id)).map((e) => e.id)
    if (!hideEmptyColumns) return base
    return base.filter((id) => filteredRows.some((r) => isConnected(r.cells[id] ?? null)))
  }, [exchanges, visibleExchangeIds, hideEmptyColumns, filteredRows])

  const effectiveExchanges = useMemo(
    () => exchanges.filter((e) => effectiveExchangeIds.includes(e.id)),
    [exchanges, effectiveExchangeIds],
  )

  return (
    <div className="min-h-full bg-[radial-gradient(1200px_600px_at_30%_-20%,rgba(56,189,248,0.15),transparent_60%),radial-gradient(900px_450px_at_90%_10%,rgba(34,197,94,0.10),transparent_55%)] px-6 py-8">
      <div className="mx-auto max-w-7xl space-y-6">
        <div className="panel-surface px-5 py-4">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div className="relative w-full md:max-w-xl">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-300/80" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Varlık veya link etiketi ara (örn. ETH, HOT)"
                className="w-full rounded-xl border border-white/10 bg-black/20 px-10 py-3 text-sm text-slate-100 placeholder:text-slate-400/70 outline-none ring-0 focus:border-sky-500/50"
              />
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <TogglePill
                checked={theme === 'dark'}
                onChange={(v) => setTheme(v ? 'dark' : 'light')}
                label="Koyu/Açık"
              />
              <TogglePill
                checked={hideEmptyColumns}
                onChange={setHideEmptyColumns}
                label="Boş sütunları gizle"
              />
              <TogglePill
                checked={hideDisconnectedRows}
                onChange={setHideDisconnectedRows}
                label="Bağlantısı olmayan satırları gizle"
              />
            </div>
          </div>

          <div className="mt-4 panel-surface-2 px-4 py-3">
            <div className="flex flex-wrap items-center gap-3">
              <span className="muted text-sm">Sütunlar:</span>
              {exchanges.map((ex) => {
                const checked = visibleExchangeIds.includes(ex.id)
                return (
                  <CheckPill
                    key={ex.id}
                    checked={checked}
                    onChange={(next) => {
                      setVisibleExchangeIds((prev) => {
                        if (next) return Array.from(new Set([...prev, ex.id]))
                        return prev.filter((id) => id !== ex.id)
                      })
                    }}
                    label={ex.name}
                  />
                )
              })}
            </div>
          </div>

          <div className="mt-3 text-right text-xs text-slate-300/70">
            İpucu: Başlıklar sabit, ilk sütun sabit. Yatay kaydırıp kolay gezin.
          </div>
        </div>

        <div className="panel-surface overflow-hidden">
          <div className="overflow-x-auto">
            <table className="min-w-max w-full border-separate border-spacing-0">
              <thead>
                <tr>
                  <th
                    className={clsx(
                      'sticky left-0 top-0 z-30 w-36 border-b border-white/10 bg-slate-950/60 px-4 py-4 text-left text-sm font-semibold backdrop-blur',
                    )}
                  >
                    <span className="muted">Varlık</span>
                  </th>
                  {effectiveExchanges.map((ex) => (
                    <th
                      key={ex.id}
                      className="sticky top-0 z-20 border-b border-white/10 bg-slate-950/60 px-4 py-4 text-left text-sm font-semibold backdrop-blur"
                    >
                      <div className="flex items-center gap-3">
                        <span className="text-slate-100">{ex.name}</span>
                        <span className="inline-flex items-center rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-xs font-semibold text-slate-200/90">
                          {ex.count}
                        </span>
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>

              <tbody>
                {filteredRows.map((r) => (
                  <tr key={r.asset} className="hover:bg-white/[0.03]">
                    <td className="sticky left-0 z-10 w-36 border-b border-white/10 bg-slate-950/40 px-4 py-5 font-semibold text-slate-100 backdrop-blur">
                      {r.asset}
                    </td>

                    {effectiveExchangeIds.map((id) => {
                      const cell = r.cells[id] ?? null
                      return (
                        <td
                          key={id}
                          className="border-b border-white/10 px-4 py-5 align-middle"
                        >
                          {cell === 'x' ? (
                            <span className="text-red-500 text-lg font-bold">X</span>
                          ) : cell === null || (Array.isArray(cell) && cell.length === 0) ? (
                            <span className="text-slate-500/80">—</span>
                          ) : (
                            <div className="flex flex-wrap gap-2">
                              {cell.map((b, idx) => (
                                <Badge key={`${b.label}-${idx}`} kind={b.kind} label={b.label} />
                              ))}
                            </div>
                          )}
                        </td>
                      )
                    })}
                  </tr>
                ))}

                {filteredRows.length === 0 ? (
                  <tr>
                    <td
                      colSpan={1 + effectiveExchangeIds.length}
                      className="px-4 py-10 text-center text-sm text-slate-300/70"
                    >
                      Sonuç bulunamadı.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  )
}
