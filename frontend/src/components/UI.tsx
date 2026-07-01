// ─── Shared UI Primitives — TypeScript Edition ───────────────────────────────
import {
  useState, useCallback, createContext, useContext,
  type ReactNode, type CSSProperties,
} from 'react'
import type { AccentColor, Severity } from '../types'

// ── Color system ──────────────────────────────────────────────────────────────
export const SEV_COLORS: Record<Severity, string> = {
  NORMAL:   '#00D37F',
  WARNING:  '#FFB020',
  CRITICAL: '#F04438',
}

const ACCENT: Record<AccentColor, { rgb: string; hex: string }> = {
  green:  { rgb: '0,211,127',   hex: '#00D37F' },
  amber:  { rgb: '255,176,32',  hex: '#FFB020' },
  red:    { rgb: '240,68,56',   hex: '#F04438' },
  blue:   { rgb: '79,124,246',  hex: '#4F7CF6' },
  teal:   { rgb: '6,182,212',   hex: '#06B6D4' },
  purple: { rgb: '167,139,250', hex: '#A78BFA' },
}

// ── MetricCard ────────────────────────────────────────────────────────────────
interface MetricCardProps {
  value:  string | number
  label:  string
  sub?:   string
  color?: AccentColor
  icon?:  ReactNode
  trend?: { delta: number; positive: boolean }
}

export function MetricCard({ value, label, sub, color = 'green', icon, trend }: MetricCardProps) {
  const a = ACCENT[color] ?? ACCENT.green
  return (
    <div
      className="animate-card-in"
      style={{
        position: 'relative', overflow: 'hidden', borderRadius: 16, padding: '18px 20px',
        background: 'linear-gradient(145deg,rgba(18,20,31,.98) 0%,rgba(13,15,24,.98) 100%)',
        border: '1px solid rgba(37,40,64,.8)',
        transition: 'border-color .22s, transform .28s cubic-bezier(.34,1.56,.64,1), box-shadow .22s',
        cursor: 'default',
      }}
      onMouseEnter={e => {
        const el = e.currentTarget
        el.style.borderColor = `rgba(${a.rgb},.4)`
        el.style.transform   = 'translateY(-3px) scale(1.01)'
        el.style.boxShadow   = `0 14px 44px rgba(0,0,0,.32),0 0 0 1px rgba(${a.rgb},.07),0 0 32px rgba(${a.rgb},.05)`
      }}
      onMouseLeave={e => {
        const el = e.currentTarget
        el.style.borderColor = 'rgba(37,40,64,.8)'
        el.style.transform   = 'translateY(0) scale(1)'
        el.style.boxShadow   = 'none'
      }}
    >
      <div style={{ position:'absolute',inset:0,pointerEvents:'none', background:`radial-gradient(ellipse at 50% -10%,rgba(${a.rgb},.1) 0%,transparent 65%)` }}/>
      <div style={{ position:'absolute',top:0,left:0,right:0,height:'1px', background:`linear-gradient(90deg,transparent,rgba(${a.rgb},.75),transparent)` }}/>
      <div style={{ position:'absolute',bottom:-18,right:-18,width:72,height:72,borderRadius:'50%',pointerEvents:'none', background:`radial-gradient(circle,rgba(${a.rgb},.07) 0%,transparent 70%)` }}/>
      <div style={{ position:'relative' }}>
        <div style={{ display:'flex',alignItems:'center',justifyContent:'space-between',marginBottom:11 }}>
          <div style={{ display:'flex',alignItems:'center',gap:7 }}>
            {icon && (
              <span style={{ width:22,height:22,borderRadius:6,flexShrink:0, background:`rgba(${a.rgb},.1)`,border:`1px solid rgba(${a.rgb},.16)`, display:'flex',alignItems:'center',justifyContent:'center',fontSize:11,color:a.hex }}>
                {icon}
              </span>
            )}
            <span style={{ fontSize:10,fontWeight:700,color:'#525870',textTransform:'uppercase',letterSpacing:'1px' }}>{label}</span>
          </div>
          {trend && (
            <span style={{ fontSize:10,fontWeight:700,letterSpacing:'.3px', color:trend.positive?'#00D37F':'#F04438', display:'flex',alignItems:'center',gap:2, background:trend.positive?'rgba(0,211,127,.08)':'rgba(240,68,56,.08)', padding:'1px 6px',borderRadius:99 }}>
              {trend.positive ? '↑' : '↓'} {Math.abs(trend.delta).toFixed(1)}%
            </span>
          )}
        </div>
        <div style={{ fontSize:30,fontWeight:900,color:'#E8ECF1',letterSpacing:'-1.2px',lineHeight:1,marginBottom:7,fontVariantNumeric:'tabular-nums' }}>{value}</div>
        {sub && <div style={{ fontSize:11,color:'#525870',fontFamily:'JetBrains Mono,monospace' }}>{sub}</div>}
      </div>
    </div>
  )
}

// ── SkeletonCard ──────────────────────────────────────────────────────────────
export function SkeletonCard() {
  return (
    <div style={{ borderRadius:16,padding:'18px 20px', background:'linear-gradient(145deg,rgba(18,20,31,.98),rgba(13,15,24,.98))', border:'1px solid rgba(37,40,64,.8)' }}>
      <div className="skeleton" style={{ height:9,width:'52%',marginBottom:14 }}/>
      <div className="skeleton" style={{ height:30,width:'38%',marginBottom:10 }}/>
      <div className="skeleton" style={{ height:8,width:'62%' }}/>
    </div>
  )
}

// ── PageHeader ────────────────────────────────────────────────────────────────
interface PageHeaderProps {
  title:       string
  subtitle?:   string
  breadcrumb:  string
  badge?:      string
}

export function PageHeader({ title, subtitle, breadcrumb, badge }: PageHeaderProps) {
  const now = new Date().toLocaleString('fr-FR', { day:'2-digit',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit' })
  return (
    <div style={{ display:'flex',alignItems:'flex-end',justifyContent:'space-between', paddingTop:28,paddingBottom:20,marginBottom:24, borderBottom:'1px solid rgba(30,34,64,.9)',position:'relative' }}>
      <div style={{ position:'absolute',bottom:-1,left:0,width:200,height:1, background:'linear-gradient(90deg,#00D37F,rgba(0,211,127,.25),transparent)' }}/>
      <div>
        <div style={{ display:'flex',alignItems:'center',gap:5,marginBottom:9, fontSize:10,fontWeight:600,color:'#3D4260',textTransform:'uppercase',letterSpacing:'1.3px' }}>
          OCP Bionic
          <svg width="7" height="7" viewBox="0 0 7 7" fill="none"><path d="M1.5 1l3 2.5-3 2.5" stroke="#3D4260" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
          <span style={{ color:'#525870' }}>{breadcrumb}</span>
        </div>
        <h1 style={{ margin:0,fontSize:27,fontWeight:900,letterSpacing:'-1.1px',lineHeight:1, background:'linear-gradient(135deg,#E8ECF1 30%,rgba(139,146,169,.7) 100%)', WebkitBackgroundClip:'text',WebkitTextFillColor:'transparent' }}>{title}</h1>
        {subtitle && <p style={{ margin:'7px 0 0',fontSize:12,color:'#525870',letterSpacing:'.1px',lineHeight:1.5 }}>{subtitle}</p>}
      </div>
      <div style={{ display:'flex',alignItems:'center',gap:8 }}>
        {badge && (
          <span style={{ display:'inline-flex',alignItems:'center',gap:6,fontSize:10,fontWeight:700,letterSpacing:'.5px', padding:'4px 11px',borderRadius:99, background:'rgba(0,211,127,.07)',border:'1px solid rgba(0,211,127,.2)',color:'#00D37F',boxShadow:'0 0 18px rgba(0,211,127,.07)' }}>
            <span style={{ width:5,height:5,background:'#00D37F',borderRadius:'50%',animation:'pulse-dot 2.5s ease-in-out infinite' }}/>
            {badge}
          </span>
        )}
        <span style={{ fontSize:10,fontFamily:'JetBrains Mono,monospace',padding:'4px 11px',borderRadius:99, color:'#525870',background:'rgba(18,20,31,.9)',border:'1px solid rgba(37,40,64,.8)',letterSpacing:'.3px' }}>{now}</span>
      </div>
    </div>
  )
}

// ── SectionHead ───────────────────────────────────────────────────────────────
interface SectionHeadProps { children: ReactNode; action?: ReactNode }
export function SectionHead({ children, action }: SectionHeadProps) {
  return (
    <div style={{ display:'flex',alignItems:'center',justifyContent:'space-between',margin:'28px 0 13px' }}>
      <div style={{ display:'flex',alignItems:'center',gap:9 }}>
        <div style={{ width:3,height:15,background:'linear-gradient(180deg,#00D37F,rgba(0,211,127,.25))',borderRadius:3,flexShrink:0 }}/>
        <span style={{ fontSize:10,fontWeight:800,color:'#6B7280',textTransform:'uppercase',letterSpacing:'1.4px' }}>{children}</span>
        <div style={{ width:80,height:1,background:'linear-gradient(90deg,rgba(37,40,64,.9),transparent)' }}/>
      </div>
      {action}
    </div>
  )
}

// ── StatusPill ────────────────────────────────────────────────────────────────
const PILL_CFG: Record<string, { bg:string; border:string; color:string }> = {
  NORMAL:   { bg:'rgba(0,211,127,.08)',  border:'rgba(0,211,127,.22)',  color:'#00D37F' },
  WARNING:  { bg:'rgba(255,176,32,.08)', border:'rgba(255,176,32,.22)', color:'#FFB020' },
  CRITICAL: { bg:'rgba(240,68,56,.08)',  border:'rgba(240,68,56,.22)',  color:'#F04438' },
  INFO:     { bg:'rgba(79,124,246,.08)', border:'rgba(79,124,246,.22)', color:'#4F7CF6' },
}

export function StatusPill({ status }: { status: string }) {
  const s = PILL_CFG[status] ?? PILL_CFG['NORMAL']
  return (
    <span style={{ display:'inline-flex',alignItems:'center',gap:5,fontSize:10,fontWeight:700,letterSpacing:'.5px',padding:'2px 9px',borderRadius:99, background:s.bg,border:`1px solid ${s.border}`,color:s.color,textTransform:'uppercase',whiteSpace:'nowrap' }}>
      <span style={{ width:5,height:5,borderRadius:'50%',background:s.color,flexShrink:0 }}/>
      {status}
    </span>
  )
}

// ── Alert ─────────────────────────────────────────────────────────────────────
interface AlertProps { msg: string; kind?: 'ok' | 'warn' | 'info' | 'err' }
const ALERT_CFG = {
  ok:   { bg:'rgba(0,211,127,.05)',  border:'rgba(0,211,127,.15)',  color:'#4DFFA9', iconBg:'rgba(0,211,127,.1)',  icon:'✓' },
  warn: { bg:'rgba(255,176,32,.05)', border:'rgba(255,176,32,.15)', color:'#FFD166', iconBg:'rgba(255,176,32,.1)', icon:'⚠' },
  info: { bg:'rgba(79,124,246,.05)', border:'rgba(79,124,246,.15)', color:'#93B4F8', iconBg:'rgba(79,124,246,.1)', icon:'ℹ' },
  err:  { bg:'rgba(240,68,56,.05)',  border:'rgba(240,68,56,.15)',  color:'#F87171', iconBg:'rgba(240,68,56,.1)',  icon:'✕' },
}

export function Alert({ msg, kind = 'info' }: AlertProps) {
  const s = ALERT_CFG[kind]
  return (
    <div style={{ display:'flex',gap:12,alignItems:'flex-start',padding:'12px 15px',borderRadius:12,margin:'8px 0', background:s.bg,border:`1px solid ${s.border}` }}>
      <span style={{ width:22,height:22,borderRadius:6,flexShrink:0,background:s.iconBg,display:'flex',alignItems:'center',justifyContent:'center',fontSize:12,color:s.color }}>{s.icon}</span>
      <div style={{ fontSize:13,color:s.color,lineHeight:1.65 }} dangerouslySetInnerHTML={{ __html: msg }}/>
    </div>
  )
}

// ── Gauge ─────────────────────────────────────────────────────────────────────
interface GaugeProps { score?: number; severity?: Severity }
export function Gauge({ score = 0, severity = 'NORMAL' }: GaugeProps) {
  const pct    = Math.min(Math.max(score, 0), 1)
  const color  = SEV_COLORS[severity] ?? '#00D37F'
  // 240° arc: starts at 150° (lower-left), ends at 390°=30° (lower-right)
  // Gap of 120° at the bottom — classic speedometer shape, perfectly symmetric
  const SIZE = 160, R = 62, CX = 80, CY = 80
  const START = 150  // degrees
  const SPAN  = 240  // degrees total arc
  const gradId = `gg-${severity}`

  function pt(deg: number) {
    const r = (deg * Math.PI) / 180
    return [CX + R * Math.cos(r), CY + R * Math.sin(r)] as [number, number]
  }
  function arcPath(p: number): string {
    const [x1, y1] = pt(START)
    const endDeg   = START + p * SPAN
    const [x2, y2] = pt(endDeg)
    const large    = p * SPAN > 180 ? 1 : 0
    return `M ${x1} ${y1} A ${R} ${R} 0 ${large} 1 ${x2} ${y2}`
  }
  function tickPath(p: number): string {
    const [ox, oy] = pt(START + p * SPAN)
    const [ix, iy] = pt(START + p * SPAN)
    const deg = START + p * SPAN
    const r   = (deg * Math.PI) / 180
    const ox2 = CX + (R - 8) * Math.cos(r), oy2 = CY + (R - 8) * Math.sin(r)
    const ix2 = CX + (R + 2) * Math.cos(r), iy2 = CY + (R + 2) * Math.sin(r)
    void ox; void oy; void ix; void iy
    return `M ${ox2} ${oy2} L ${ix2} ${iy2}`
  }

  return (
    <div style={{ display:'flex', flexDirection:'column', alignItems:'center', gap:6 }}>
      <svg
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        width={SIZE} height={SIZE}
        style={{ display:'block', overflow:'visible' }}
      >
        <defs>
          <linearGradient id={gradId} x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%"   stopColor={color} stopOpacity=".4"/>
            <stop offset="100%" stopColor={color} stopOpacity="1"/>
          </linearGradient>
        </defs>

        {/* Track (full 240°) */}
        <path d={arcPath(1)} fill="none" stroke="rgba(37,40,64,.85)"
              strokeWidth={10} strokeLinecap="round"/>

        {/* Filled arc */}
        {pct > 0 && (
          <path d={arcPath(pct)} fill="none" stroke={`url(#${gradId})`}
                strokeWidth={10} strokeLinecap="round"
                style={{ filter:`drop-shadow(0 0 8px ${color}70)` }}/>
        )}

        {/* Tick marks at 0%, 25%, 50%, 75%, 100% */}
        {[0, .25, .5, .75, 1].map(p => (
          <path key={p} d={tickPath(p)} fill="none"
                stroke="rgba(30,33,58,.95)" strokeWidth={2}/>
        ))}

        {/* Score — centered inside circle */}
        <text
          x={CX} y={CY - 6}
          textAnchor="middle" dominantBaseline="middle"
          fontSize={26} fontWeight={900} fill={color}
          fontFamily="Inter,sans-serif"
        >
          {(pct * 100).toFixed(1)}%
        </text>
        <text
          x={CX} y={CY + 16}
          textAnchor="middle" dominantBaseline="middle"
          fontSize={8} fill="#525870"
          fontFamily="Inter,sans-serif" letterSpacing="1.5"
        >
          SCORE ANOMALIE
        </text>
      </svg>

      <StatusPill status={severity}/>
    </div>
  )
}

// ── Spinner ───────────────────────────────────────────────────────────────────
export function Spinner() {
  return (
    <div style={{ display:'flex',flexDirection:'column',alignItems:'center',justifyContent:'center',gap:10,height:140 }}>
      <div style={{ width:34,height:34,borderRadius:'50%',border:'2.5px solid rgba(0,211,127,.1)',borderTopColor:'#00D37F',animation:'spin .7s linear infinite' }}/>
      <span style={{ fontSize:10,color:'#3D4260',fontFamily:'JetBrains Mono,monospace',letterSpacing:'.5px' }}>Chargement…</span>
    </div>
  )
}

// ── ChartCard ─────────────────────────────────────────────────────────────────
interface ChartCardProps { children: ReactNode; title?: string; action?: ReactNode; className?: string }
export function ChartCard({ children, title, action, className = '' }: ChartCardProps) {
  return (
    <div className={`rounded-xl overflow-hidden ${className}`} style={{ background:'rgba(13,15,24,.72)',border:'1px solid rgba(37,40,64,.7)',boxShadow:'0 4px 20px rgba(0,0,0,.18)' }}>
      {(title ?? action) && (
        <div style={{ display:'flex',alignItems:'center',justifyContent:'space-between',padding:'11px 16px 4px' }}>
          {title && <span style={{ fontSize:11,fontWeight:600,color:'#6B7280',letterSpacing:'.3px' }}>{title}</span>}
          {action}
        </div>
      )}
      <div style={{ padding:title ? '6px 12px 13px' : 12 }}>{children}</div>
    </div>
  )
}

// ── Select ────────────────────────────────────────────────────────────────────
interface SelectOption { v: string | number; l: string }
interface SelectProps  { label?: string; value: string | number; onChange: (v: string) => void; options: SelectOption[] }
export function Select({ label, value, onChange, options }: SelectProps) {
  const focusStyle: CSSProperties = { borderColor:'rgba(0,211,127,.4)',boxShadow:'0 0 0 3px rgba(0,211,127,.07)' }
  return (
    <div>
      {label && <label style={{ fontSize:9,fontWeight:800,color:'#525870',textTransform:'uppercase',letterSpacing:'1.2px',display:'block',marginBottom:6 }}>{label}</label>}
      <select value={value} onChange={e => onChange(e.target.value)}
        style={{ background:'rgba(18,20,31,.9)',border:'1px solid rgba(37,40,64,.8)',borderRadius:10,color:'#E8ECF1',fontSize:13,padding:'8px 12px',outline:'none',width:'100%',cursor:'pointer',transition:'border-color .15s, box-shadow .15s',fontFamily:'inherit' }}
        onFocus={e => { Object.assign(e.target.style, focusStyle) }}
        onBlur={e  => { e.target.style.borderColor='rgba(37,40,64,.8)'; e.target.style.boxShadow='none' }}>
        {options.map(o => <option key={o.v} value={o.v} style={{ background:'#12141f' }}>{o.l}</option>)}
      </select>
    </div>
  )
}

// ── Toast system ──────────────────────────────────────────────────────────────
type ToastKind = 'ok' | 'warn' | 'info' | 'err'
type PushFn = (msg: string, kind?: ToastKind, duration?: number) => void

const ToastCtx = createContext<PushFn | null>(null)

interface Toast { id: number; msg: string; kind: ToastKind }
const TOAST_CFG: Record<ToastKind, { border: string; icon: string; color: string }> = {
  ok:   { border:'rgba(0,211,127,.3)',  icon:'✓', color:'#00D37F' },
  warn: { border:'rgba(255,176,32,.3)', icon:'⚠', color:'#FFB020' },
  info: { border:'rgba(79,124,246,.3)', icon:'ℹ', color:'#4F7CF6' },
  err:  { border:'rgba(240,68,56,.3)',  icon:'✕', color:'#F04438' },
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const push = useCallback<PushFn>((msg, kind = 'info', duration = 4000) => {
    const id = Date.now() + Math.random()
    setToasts(t => [...t, { id, msg, kind }])
    setTimeout(() => setToasts(t => t.filter(x => x.id !== id)), duration)
  }, [])

  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div style={{ position:'fixed',bottom:24,right:24,zIndex:9999,display:'flex',flexDirection:'column',gap:8,pointerEvents:'none' }}>
        {toasts.map(t => {
          const s = TOAST_CFG[t.kind]
          return (
            <div key={t.id} style={{ display:'flex',alignItems:'center',gap:10,padding:'10px 16px',borderRadius:11,minWidth:240, background:'rgba(13,15,24,.97)',backdropFilter:'blur(16px)',border:`1px solid ${s.border}`, boxShadow:'0 10px 36px rgba(0,0,0,.45)',animation:'toast-in .28s cubic-bezier(.34,1.56,.64,1) forwards',pointerEvents:'all' }}>
              <span style={{ width:20,height:20,borderRadius:5,flexShrink:0,display:'flex',alignItems:'center',justifyContent:'center',fontSize:11,color:s.color }}>{s.icon}</span>
              <span style={{ fontSize:12,color:'#C8CDD8',lineHeight:1.5 }}>{t.msg}</span>
            </div>
          )
        })}
      </div>
    </ToastCtx.Provider>
  )
}

export function useToast(): PushFn {
  const ctx = useContext(ToastCtx)
  if (!ctx) throw new Error('useToast must be used inside ToastProvider')
  return ctx
}
