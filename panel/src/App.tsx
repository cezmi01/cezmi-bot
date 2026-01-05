import { Link, Search, X } from 'lucide-react'
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

type WalletLinks = Record<
  string,
  Record<
    string,
    {
      hot?: [string?, string?, string?, string?]
      cold?: string
    }
  >
>

type AssetRow = {
  asset: string
  cells: Record<string, CellValue>
}

const WALLET_LINKS_STORAGE_KEY = 'walletLinks:v3'
const DEFAULT_ASSET_KEY = '__default__'

function normalizeUrl(url: string) {
  const trimmed = url.trim()
  if (!trimmed) return ''
  if (/^https?:\/\//i.test(trimmed)) return trimmed
  return `https://${trimmed}`
}

function loadWalletLinks(): WalletLinks {
  try {
    const raw = localStorage.getItem(WALLET_LINKS_STORAGE_KEY)
    if (!raw) return {}
    const parsed: unknown = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object') return {}
    return parsed as WalletLinks
  } catch {
    return {}
  }
}

function saveWalletLinks(links: WalletLinks) {
  localStorage.setItem(WALLET_LINKS_STORAGE_KEY, JSON.stringify(links))
}

function migrateWalletLinksFromOlderIfNeeded(): WalletLinks {
  // v3 varsa onu kullan
  const existingV3 = loadWalletLinks()
  if (Object.keys(existingV3).length > 0) return existingV3

  const toHot4 = (hot?: string) => (hot ? ([hot, '', '', ''] as [string?, string?, string?, string?]) : undefined)

  // v2 (exchange -> asset -> {hot, cold}) varsa onu v3'e çevir
  try {
    const rawV2 = localStorage.getItem('walletLinks:v2')
    if (rawV2) {
      const parsed: unknown = JSON.parse(rawV2)
      if (parsed && typeof parsed === 'object') {
        const v2 = parsed as Record<string, Record<string, { hot?: string; cold?: string }>>
        const migrated: WalletLinks = {}
        for (const [exchangeId, assets] of Object.entries(v2)) {
          migrated[exchangeId] = {}
          for (const [asset, links] of Object.entries(assets)) {
            migrated[exchangeId][asset] = { hot: toHot4(links.hot), cold: links.cold ?? '' }
          }
        }
        saveWalletLinks(migrated)
        return migrated
      }
    }
  } catch {
    // ignore
  }

  // v1 (exchange -> {hot,cold}) varsa onu varsayılan olarak içeri al
  try {
    const rawV1 = localStorage.getItem('walletLinks:v1')
    if (!rawV1) return {}
    const parsed: unknown = JSON.parse(rawV1)
    if (!parsed || typeof parsed !== 'object') return {}
    const v1 = parsed as Record<string, { hot?: string; cold?: string }>
    const migrated: WalletLinks = {}
    for (const [exchangeId, links] of Object.entries(v1)) {
      migrated[exchangeId] = {
        [DEFAULT_ASSET_KEY]: { hot: toHot4(links.hot), cold: links.cold ?? '' },
      }
    }
    saveWalletLinks(migrated)
    return migrated
  } catch {
    return {}
  }
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

function Badge({
  kind,
  label,
  href,
}: CellItem & {
  href?: string
}) {
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

  const content = (
    <>
      <span className={clsx('h-2 w-2 rounded-full', palette.dot)} />
      <span>{label}</span>
      {href ? (
        <span className="ml-1 inline-flex items-center text-slate-300/70">
          <Link className="h-3.5 w-3.5" />
        </span>
      ) : null}
    </>
  )

  return (
    <span className="inline-flex">
      {href ? (
        <a
          href={href}
          target="_blank"
          rel="noreferrer"
          className={clsx(
            'inline-flex items-center gap-2 rounded-full border border-white/10 px-3 py-1 text-xs font-semibold',
            'hover:border-sky-500/40 hover:bg-white/10',
            palette.bg,
            palette.text,
          )}
        >
          {content}
        </a>
      ) : (
        <span
          className={clsx(
            'inline-flex items-center gap-2 rounded-full border border-white/10 px-3 py-1 text-xs font-semibold',
            palette.bg,
            palette.text,
          )}
        >
          {content}
        </span>
      )}
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

function badgeWalletType(badge: CellItem): 'hot' | 'cold' | null {
  if (badge.kind === 'hot') return 'hot'
  if (badge.kind === 'cold') return 'cold'
  // güvenlik: etiketle de yakala (HOT-14 gibi)
  const upper = badge.label.trim().toUpperCase()
  if (upper === 'HOT' || upper.startsWith('HOT-')) return 'hot'
  if (upper === 'COLD' || upper.startsWith('COLD-')) return 'cold'
  return null
}

function getExplicitLinksForAsset(links: WalletLinks, exchangeId: string, asset: string) {
  const entry = links[exchangeId]?.[asset]
  const hot = entry?.hot ?? ['', '', '', '']
  const cold = entry?.cold ?? ''

  const hotNormalized = [0, 1, 2, 3].map((i) => normalizeUrl(hot[i as 0 | 1 | 2 | 3] ?? '')).filter(Boolean)
  const coldNormalized = normalizeUrl(cold)

  return {
    hot: hotNormalized,
    cold: coldNormalized || '',
    hasAny: hotNormalized.length > 0 || Boolean(coldNormalized),
  }
}

function getWalletHrefForAsset(
  links: WalletLinks,
  exchangeId: string,
  asset: string,
  walletType: 'hot' | 'cold',
  hotIndex?: 0 | 1 | 2 | 3,
) {
  const perAsset = links[exchangeId]?.[asset]
  const perDefault = links[exchangeId]?.[DEFAULT_ASSET_KEY]

  if (walletType === 'cold') {
    const raw = perAsset?.cold ?? perDefault?.cold ?? ''
    const normalized = raw ? normalizeUrl(raw) : ''
    return normalized || undefined
  }

  const idx = hotIndex ?? 0
  const raw = perAsset?.hot?.[idx] ?? perDefault?.hot?.[idx] ?? ''
  const normalized = raw ? normalizeUrl(raw) : ''
  return normalized || undefined
}

function Modal({
  open,
  title,
  onClose,
  children,
}: {
  open: boolean
  title: string
  onClose: () => void
  children: React.ReactNode
}) {
  useEffect(() => {
    if (!open) return
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [open, onClose])

  if (!open) return null
  return (
    <div className="fixed inset-0 z-50">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <div className="absolute inset-x-0 top-10 mx-auto w-[min(920px,calc(100%-2rem))]">
        <div className="panel-surface overflow-hidden">
          <div className="flex items-center justify-between border-b border-white/10 px-5 py-4">
            <div className="text-sm font-semibold text-slate-100">{title}</div>
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-white/10 bg-white/5 p-2 text-slate-200 hover:bg-white/10"
              aria-label="Kapat"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="max-h-[70vh] overflow-auto px-5 py-4">{children}</div>
        </div>
      </div>
    </div>
  )
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
    () => {
      const initial: AssetRow[] = [
        {
          asset: 'CHZ',
          cells: {
            btcturk: [
              { kind: 'hot', label: 'HOT' },
              { kind: 'cold', label: 'COLD' },
            ],
            paribu: null,
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
            paribu: null,
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
            paribu: null,
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
            paribu: null,
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
            paribu: [{ kind: 'waiting', label: 'Bekleniyor' }],
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
            paribu: null,
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
      ]

      // Coin listesi (senin verdiğin): ARB, FLR, ADA, BASE, BTC, DASH, DOGE, DOT, DYM, ENJ, EOS, ETC, ETHW,
      // FIL, FLOW, GLMR, HBAR, ICP, INJ, KAVA, KSM, LTC, LUNA, MANTA, MINA, IOTA, MNT, NEAR, NEO, ONT,
      // OP, POL, RVN, SEI, SONIC, STX, SUI, THETA, THOR, TIA, TON, VANA,
      // VET, WAVES, XLM, XRP, XTZ, ZIL, ZK, 0G, XPL, TAO, BERA, BCH, ALGO, ATOM, APT, AXL, DYDX, MANTRA, MONAD
      //
      // Notlar:
      // - "ICP,," gibi tekrar/boşları temizliyoruz.
      // - "SEİ/SUİ/SONİC/TİA" gibi yazımlar ticker'a uygun şekilde SEI/SUI/SONIC/TIA yapılır.
      // - "KSMLTC" girişi KSM + LTC olarak ayrılır.
      const raw = [
        'ARB',
        'FLR',
        'ADA',
        'BASE',
        'BTC',
        'DASH',
        'DOGE',
        'DOT',
        'DYM',
        'ENJ',
        'EOS',
        'ETC',
        'ETHW',
        'FIL',
        'FLOW',
        'GLMR',
        'HBAR',
        'ICP',
        'INJ',
        'ICP',
        '',
        'KAVA',
        'KSMLTC',
        'LUNA',
        'MANTA',
        'MINA',
        'IOTA',
        'MNT',
        'NEAR',
        'NEO',
        'ONT',
        'OP',
        'POL',
        'RVN',
        'SEİ',
        'SONİC',
        'STX',
        'SUİ',
        'THETA',
        'THOR',
        'TİA',
        'TON',
        'VANA',
        'VET',
        'WAVES',
        'XLM',
        'XRP',
        'XTZ',
        'ZIL',
        'ZK',
        '0G',
        'XPL',
        'TAO',
        'BERA',
        'BCH',
        'ALGO',
        'ATOM',
        'APT',
        'AXL',
        'DYDX',
        'MANTRA',
        'MONAD',
        '',
      ]

      const normalizeTicker = (s: string) =>
        s
          .trim()
          .replaceAll('İ', 'I')
          .replaceAll('ı', 'i')
          .toUpperCase()

      const out: string[] = []
      for (const item of raw) {
        const t = normalizeTicker(item)
        if (!t) continue
        if (t === 'KSMLTC') {
          out.push('KSM', 'LTC')
          continue
        }
        out.push(t)
      }

      const unique = Array.from(new Set(out))
      const initialSet = new Set(initial.map((r) => r.asset))
      const additional = unique.filter((a) => !initialSet.has(a))

      const emptyCells = {
        btcturk: null,
        paribu: null,
        binance: null,
        okx: null,
        bybit: null,
        gate: null,
        mexc: null,
        bitget: null,
        kucoin: null,
        coinbase: null,
      } as const

      return [
        ...initial,
        ...additional.map(
        (asset): AssetRow => ({
          asset,
          cells: { ...emptyCells },
        }),
        ),
      ]
    },
    [],
  )

  const [query, setQuery] = useState('')
  const [hideEmptyColumns, setHideEmptyColumns] = useState(false)
  const [hideDisconnectedRows, setHideDisconnectedRows] = useState(false)
  const [walletLinks, setWalletLinks] = useState<WalletLinks>(() => migrateWalletLinksFromOlderIfNeeded())
  const [linksOpen, setLinksOpen] = useState(false)

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

  const assets = useMemo(() => rows.map((r) => r.asset), [rows])

  return (
    <div className="h-[100dvh] w-screen overflow-hidden bg-[radial-gradient(1200px_600px_at_30%_-20%,rgba(56,189,248,0.15),transparent_60%),radial-gradient(900px_450px_at_90%_10%,rgba(34,197,94,0.10),transparent_55%)] p-4 md:p-6">
      <div className="flex h-full w-full flex-col gap-4">
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
              <button
                type="button"
                onClick={() => setLinksOpen(true)}
                className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-slate-100 hover:bg-white/10"
              >
                <Link className="h-4 w-4 text-slate-200/90" />
                Cüzdan linkleri
              </button>
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

        <Modal open={linksOpen} title="Borsa cüzdan linkleri (HOT / COLD)" onClose={() => setLinksOpen(false)}>
          <div className="muted text-sm">
            Buraya sadece web linklerini gir. Kaydedince tarayıcıya (localStorage) yazılır; HOT/COLD rozetlerine tıklayınca
            yeni sekmede açılır.
          </div>

          <div className="mt-4 grid gap-3">
            {exchanges.map((ex) => {
              const defHot = walletLinks[ex.id]?.[DEFAULT_ASSET_KEY]?.hot ?? ['', '', '', '']
              const defCold = walletLinks[ex.id]?.[DEFAULT_ASSET_KEY]?.cold ?? ''
              return (
                <div key={ex.id} className="panel-surface-2 px-4 py-4">
                  <div className="mb-3 flex items-center justify-between">
                    <div className="text-sm font-semibold text-slate-100">{ex.name}</div>
                    <div className="text-xs text-slate-300/70">{ex.id}</div>
                  </div>

                  <div className="grid gap-3 md:grid-cols-2">
                    <label className="grid gap-2">
                      <span className="text-xs font-semibold text-slate-200">
                        Varsayılan HOT linkler (tüm varlıklar)
                      </span>
                      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                        {[0, 1, 2, 3].map((i) => (
                          <input
                            key={i}
                            value={defHot[i] ?? ''}
                            onChange={(e) => {
                              const next = e.target.value
                              setWalletLinks((prev) => {
                                const existing = prev[ex.id]?.[DEFAULT_ASSET_KEY]?.hot ?? ['', '', '', '']
                                const hot = [...existing] as [string?, string?, string?, string?]
                                hot[i as 0 | 1 | 2 | 3] = next
                                return {
                                  ...prev,
                                  [ex.id]: {
                                    ...(prev[ex.id] ?? {}),
                                    [DEFAULT_ASSET_KEY]: {
                                      ...(prev[ex.id]?.[DEFAULT_ASSET_KEY] ?? {}),
                                      hot,
                                    },
                                  },
                                }
                              })
                            }}
                            placeholder={`HOT-${i + 1} https://...`}
                            className="w-full rounded-xl border border-white/10 bg-black/20 px-4 py-2 text-sm text-slate-100 placeholder:text-slate-400/70 outline-none focus:border-sky-500/50"
                          />
                        ))}
                      </div>
                    </label>

                    <label className="grid gap-2">
                      <span className="text-xs font-semibold text-slate-200">
                        Varsayılan COLD link (tüm varlıklar)
                      </span>
                      <input
                        value={defCold}
                        onChange={(e) => {
                          const next = e.target.value
                          setWalletLinks((prev) => ({
                            ...prev,
                            [ex.id]: {
                              ...(prev[ex.id] ?? {}),
                              [DEFAULT_ASSET_KEY]: {
                                ...(prev[ex.id]?.[DEFAULT_ASSET_KEY] ?? {}),
                                cold: next,
                              },
                            },
                          }))
                        }}
                        placeholder="https://..."
                        className="w-full rounded-xl border border-white/10 bg-black/20 px-4 py-2 text-sm text-slate-100 placeholder:text-slate-400/70 outline-none focus:border-sky-500/50"
                      />
                    </label>
                  </div>

                  <div className="mt-4 overflow-x-auto">
                    <table className="min-w-[760px] w-full border-separate border-spacing-0">
                      <thead>
                        <tr>
                          <th className="sticky left-0 bg-slate-950/10 px-2 py-2 text-left text-xs font-semibold text-slate-200">
                            Varlık
                          </th>
                          <th className="px-2 py-2 text-left text-xs font-semibold text-slate-200">HOT</th>
                          <th className="px-2 py-2 text-left text-xs font-semibold text-slate-200">COLD</th>
                        </tr>
                      </thead>
                      <tbody>
                        {assets.map((asset) => {
                          const hot = walletLinks[ex.id]?.[asset]?.hot ?? ['', '', '', '']
                          const cold = walletLinks[ex.id]?.[asset]?.cold ?? ''
                          return (
                            <tr key={asset} className="border-t border-white/10">
                              <td className="sticky left-0 bg-slate-950/10 px-2 py-2 text-sm font-semibold text-slate-100">
                                {asset}
                              </td>
                              <td className="px-2 py-2">
                                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                                  {[0, 1, 2, 3].map((i) => (
                                    <input
                                      key={i}
                                      value={hot[i] ?? ''}
                                      onChange={(e) => {
                                        const next = e.target.value
                                        setWalletLinks((prev) => {
                                          const existing = prev[ex.id]?.[asset]?.hot ?? ['', '', '', '']
                                          const nextHot = [...existing] as [string?, string?, string?, string?]
                                          nextHot[i as 0 | 1 | 2 | 3] = next
                                          return {
                                            ...prev,
                                            [ex.id]: {
                                              ...(prev[ex.id] ?? {}),
                                              [asset]: { ...(prev[ex.id]?.[asset] ?? {}), hot: nextHot },
                                            },
                                          }
                                        })
                                      }}
                                      placeholder={`HOT-${i + 1} (boş: varsayılan)`}
                                      className="w-full rounded-xl border border-white/10 bg-black/20 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-400/70 outline-none focus:border-sky-500/50"
                                    />
                                  ))}
                                </div>
                              </td>
                              <td className="px-2 py-2">
                                <input
                                  value={cold}
                                  onChange={(e) => {
                                    const next = e.target.value
                                    setWalletLinks((prev) => ({
                                      ...prev,
                                      [ex.id]: {
                                        ...(prev[ex.id] ?? {}),
                                        [asset]: { ...(prev[ex.id]?.[asset] ?? {}), cold: next },
                                      },
                                    }))
                                  }}
                                  placeholder="(boş bırak: varsayılanı kullan)"
                                  className="w-full rounded-xl border border-white/10 bg-black/20 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-400/70 outline-none focus:border-sky-500/50"
                                />
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              )
            })}
          </div>

          <div className="mt-4 flex flex-wrap items-center justify-end gap-2">
            <button
              type="button"
              onClick={() => {
                setWalletLinks({})
                saveWalletLinks({})
              }}
              className="rounded-xl border border-white/10 bg-white/5 px-4 py-2 text-sm text-slate-100 hover:bg-white/10"
            >
              Temizle
            </button>
            <button
              type="button"
              onClick={() => {
                saveWalletLinks(walletLinks)
                setLinksOpen(false)
              }}
              className="rounded-xl border border-sky-500/30 bg-sky-500/15 px-4 py-2 text-sm font-semibold text-slate-100 hover:bg-sky-500/20"
            >
              Kaydet
            </button>
          </div>
        </Modal>

        <div className="panel-surface flex-1 overflow-hidden">
          <div className="h-full overflow-auto">
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
                      const explicit = getExplicitLinksForAsset(walletLinks, id, r.asset)
                      return (
                        <td
                          key={id}
                          className="border-b border-white/10 px-4 py-5 align-middle"
                        >
                          {cell === 'x' ? (
                            <span className="text-red-500 text-lg font-bold">X</span>
                          ) : cell === null || (Array.isArray(cell) && cell.length === 0) ? (
                            explicit.hasAny ? (
                              <div className="flex flex-wrap gap-2">
                                {explicit.hot.map((href, i) => (
                                  <Badge
                                    key={`hot-${i}`}
                                    kind="hot"
                                    label={i === 0 ? 'HOT' : `HOT-${i + 1}`}
                                    href={href}
                                  />
                                ))}
                                {explicit.cold ? (
                                  <Badge key="cold" kind="cold" label="COLD" href={explicit.cold} />
                                ) : null}
                              </div>
                            ) : (
                              <span className="text-slate-500/80">—</span>
                            )
                          ) : (
                            <div className="flex flex-wrap gap-2">
                              {(() => {
                                let hotIdx: 0 | 1 | 2 | 3 = 0
                                return cell.map((b, idx) => {
                                  const t = badgeWalletType(b)
                                  let href: string | undefined
                                  if (t === 'hot') {
                                    href = getWalletHrefForAsset(walletLinks, id, r.asset, 'hot', hotIdx)
                                    if (hotIdx < 3) hotIdx = ((hotIdx + 1) as 0 | 1 | 2 | 3)
                                  } else if (t === 'cold') {
                                    href = getWalletHrefForAsset(walletLinks, id, r.asset, 'cold')
                                  }
                                  return (
                                    <Badge
                                      key={`${b.label}-${idx}`}
                                      kind={b.kind}
                                      label={b.label}
                                      href={href}
                                    />
                                  )
                                })
                              })()}
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
