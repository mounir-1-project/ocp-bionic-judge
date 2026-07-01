import { useState, useEffect, type ReactNode } from 'react'
import { useApi } from '../hooks/useApi.ts'
import { api }   from '../api.ts'
import type { HealthResponse, SummaryResponse } from '../types'

// ── Lucide-style SVG icons ────────────────────────────────────────────────────
const Icons: Record<string, ReactNode> = {
  activity: (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M22 12h-4l-3 9L9 3l-3 9H2"/>
    </svg>
  ),
  bot: (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="11" width="18" height="10" rx="2"/>
      <circle cx="12" cy="5" r="2"/>
      <path d="M12 7v4M8 15h.01M16 15h.01"/>
    </svg>
  ),
  shield: (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
    </svg>
  ),
  refresh: (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/>
      <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>
    </svg>
  ),
  logOut: (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
      <polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>
    </svg>
  ),
  clock: (
    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>
    </svg>
  ),
}

type PageId = 'sensors' | 'judge' | 'governance'

interface NavItem { id: PageId; label: string; icon: ReactNode }
const NAV: NavItem[] = [
  { id: 'sensors',    label: 'Capteurs & Détection', icon: Icons.activity },
  { id: 'judge',      label: 'Judge Agent',           icon: Icons.bot      },
  { id: 'governance', label: 'Gouvernance & Audit',   icon: Icons.shield   },
]

interface SidebarProps {
  page:     PageId
  onPage:   (p: PageId) => void
  onLogout: () => void
}

export default function Sidebar({ page, onPage, onLogout }: SidebarProps) {
  const { data: health  } = useApi<HealthResponse> (() => api.health(),  [], 30_000)
  const { data: summary } = useApi<SummaryResponse>(() => api.summary(), [], 30_000)
  const [time, setTime] = useState(new Date())

  useEffect(() => {
    const id = setInterval(() => setTime(new Date()), 1000)
    return () => clearInterval(id)
  }, [])

  const isOnline = health?.status === 'ok'

  return (
    <aside style={{ width:250,flexShrink:0, background:'linear-gradient(180deg,#111320 0%,#0d0f1b 100%)', borderRight:'1px solid rgba(37,40,64,.7)', boxShadow:'4px 0 36px rgba(0,0,0,.45), inset -1px 0 0 rgba(79,124,246,.04)', display:'flex',flexDirection:'column',height:'100vh',overflowY:'auto' }}>

      {/* Logo */}
      <div style={{ padding:'22px 18px 18px' }}>
        <div style={{ display:'flex',alignItems:'center',gap:12, paddingBottom:18, borderBottom:'1px solid transparent', backgroundImage:'linear-gradient(#111320,#111320),linear-gradient(90deg,transparent,rgba(0,211,127,.28),transparent)', backgroundOrigin:'border-box',backgroundClip:'padding-box,border-box', borderBottomStyle:'solid',borderBottomWidth:1 }}>
          <div style={{ width:42,height:42,borderRadius:12,flexShrink:0, background:'linear-gradient(135deg,rgba(0,211,127,.14) 0%,rgba(0,211,127,.04) 100%)', border:'1px solid rgba(0,211,127,.22)', display:'flex',alignItems:'center',justifyContent:'center', boxShadow:'0 0 22px rgba(0,211,127,.12), inset 0 1px 0 rgba(0,211,127,.08)', position:'relative',overflow:'hidden',padding:5 }}>
            <div style={{ position:'absolute',inset:0,background:'linear-gradient(135deg,rgba(255,255,255,.05) 0%,transparent 55%)' }}/>
            <img src="/ocp_logo.png" alt="OCP" style={{ width:"100%",height:"100%",objectFit:"contain" }} onError={(e) => { const t=e.target as HTMLImageElement; t.style.display="none"; t.parentElement!.innerHTML="⚗️"; }}/>
          </div>
          <div>
            <div style={{ fontSize:14,fontWeight:800,color:'#E8ECF1',letterSpacing:'-0.3px',lineHeight:1.2 }}>Bionic Judge</div>
            <div style={{ fontSize:9.5,color:'#525870',textTransform:'uppercase',letterSpacing:'1.4px',marginTop:4, display:'flex',alignItems:'center',gap:5 }}>
              <span style={{ width:5,height:5,borderRadius:'50%',flexShrink:0, background:isOnline?'#00D37F':'#F04438', boxShadow:isOnline?'0 0 6px rgba(0,211,127,.7)':'0 0 6px rgba(240,68,56,.5)', animation:isOnline?'pulse-dot 2.5s ease-in-out infinite':'none' }}/>
              OCP · Programme Bionic
            </div>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav style={{ padding:'0 10px',flex:1 }}>
        <div style={{ fontSize:9,fontWeight:700,color:'#3D4260',textTransform:'uppercase',letterSpacing:'1.9px',padding:'4px 8px 9px' }}>Navigation</div>
        {NAV.map(n => {
          const active = page === n.id
          return (
            <button key={n.id} onClick={() => onPage(n.id)} style={{
              display:'flex',alignItems:'center',gap:10,width:'100%',textAlign:'left',
              padding:'9px 12px',marginBottom:2,border:'none',borderRadius:11,cursor:'pointer',
              fontSize:12.5,fontWeight:active?600:500,color:active?'#00D37F':'#6B7280',
              background:active?'linear-gradient(90deg,rgba(0,211,127,.11) 0%,rgba(0,211,127,.04) 100%)':'transparent',
              boxShadow:active?'inset 0 1px 0 rgba(0,211,127,.08),0 0 0 1px rgba(0,211,127,.07)':'none',
              transition:'all .18s ease',position:'relative',overflow:'hidden',
            }}
              onMouseEnter={e => { if (!active) { e.currentTarget.style.background='rgba(79,124,246,.07)'; e.currentTarget.style.color='#B8C0D4' }}}
              onMouseLeave={e => { if (!active) { e.currentTarget.style.background='transparent'; e.currentTarget.style.color='#6B7280' }}}
            >
              {active && <div style={{ position:'absolute',left:0,top:'50%',transform:'translateY(-50%)',width:3,height:18, background:'linear-gradient(180deg,#00D37F,rgba(0,211,127,.5))',borderRadius:'0 3px 3px 0',boxShadow:'0 0 12px rgba(0,211,127,.45)' }}/>}
              <span style={{ color:active?'#00D37F':'#525870',flexShrink:0,transition:'color .18s' }}>{n.icon}</span>
              {n.label}
            </button>
          )
        })}

        <div style={{ height:1,margin:'10px 4px',background:'linear-gradient(90deg,transparent,rgba(37,40,64,.8),transparent)' }}/>

        <button onClick={() => window.location.reload()} style={{ display:'flex',alignItems:'center',justifyContent:'center',gap:7, width:'100%',padding:'7px 12px',borderRadius:10,cursor:'pointer', background:'rgba(20,22,31,.6)',border:'1px solid rgba(37,40,64,.7)',color:'#525870',fontSize:11,fontWeight:500,transition:'all .15s ease' }}
          onMouseEnter={e => { e.currentTarget.style.borderColor='rgba(0,211,127,.3)';e.currentTarget.style.color='#00D37F';e.currentTarget.style.background='rgba(0,211,127,.05)' }}
          onMouseLeave={e => { e.currentTarget.style.borderColor='rgba(37,40,64,.7)';e.currentTarget.style.color='#525870';e.currentTarget.style.background='rgba(20,22,31,.6)' }}>
          {Icons.refresh} Actualiser les données
        </button>
      </nav>

      {/* System status */}
      <div style={{ margin:'12px 12px 8px',background:'rgba(9,11,18,.6)',backdropFilter:'blur(12px)', border:'1px solid rgba(37,40,64,.55)',borderRadius:14,padding:'13px 14px' }}>
        <div style={{ display:'flex',alignItems:'center',justifyContent:'space-between',marginBottom:10 }}>
          <span style={{ fontSize:9,fontWeight:700,color:'#3D4260',textTransform:'uppercase',letterSpacing:'1.9px' }}>Système</span>
          <span style={{ fontSize:9,fontWeight:700,letterSpacing:'.6px', color:isOnline?'#00D37F':'#F04438', background:isOnline?'rgba(0,211,127,.08)':'rgba(240,68,56,.08)', border:`1px solid ${isOnline?'rgba(0,211,127,.2)':'rgba(240,68,56,.2)'}`, padding:'2px 8px',borderRadius:99,display:'inline-flex',alignItems:'center',gap:4 }}>
            <span style={{ width:4,height:4,borderRadius:'50%',background:isOnline?'#00D37F':'#F04438',animation:isOnline?'pulse-dot 2.5s ease-in-out infinite':'none' }}/>
            {isOnline ? 'ONLINE' : 'OFFLINE'}
          </span>
        </div>
        {([
          { k:'DB',        v:health?.db_connected ? '✓ Connectée' : '✗ Off',        warn:!health?.db_connected },
          { k:'Modèle',    v:health?.model_loaded  ? '✓ Chargé'   : '⚠ Absent',     warn:!health?.model_loaded },
          { k:'Machines',  v:summary ? `${summary.machines_active} actives` : '—',  warn:false },
          { k:'Anomalies', v:summary ? summary.anomalies.toLocaleString() : '—',     warn:(summary?.anomalies ?? 0) > 0 },
        ] as Array<{k:string;v:string;warn:boolean}>).map(({ k, v, warn }) => (
          <div key={k} style={{ display:'flex',justifyContent:'space-between',alignItems:'center',padding:'4px 0',borderBottom:'1px solid rgba(37,40,64,.45)',fontSize:11 }}>
            <span style={{ color:'#525870' }}>{k}</span>
            <span style={{ color:warn?'#FFB020':'#C8CDD8',fontWeight:500,fontFamily:'JetBrains Mono,monospace',fontSize:10 }}>{v}</span>
          </div>
        ))}
        <div style={{ display:'flex',alignItems:'center',justifyContent:'center',gap:5,paddingTop:8,fontSize:10,fontFamily:'JetBrains Mono,monospace',color:'#3D4260',letterSpacing:'.3px' }}>
          {Icons.clock} {time.toLocaleTimeString('fr-FR')}
        </div>
      </div>

      {/* Footer */}
      <div style={{ padding:'8px 16px 18px',fontSize:10,color:'#3D4260',lineHeight:1.9 }}>
        <div style={{ display:'flex',alignItems:'center',justifyContent:'space-between' }}>
          <span>OCP Bionic Judge v1.0.0</span>
          <button onClick={onLogout} style={{ display:'inline-flex',alignItems:'center',gap:4,fontSize:10,color:'#525870', background:'none',border:'none',cursor:'pointer',padding:0,transition:'color .15s' }}
            onMouseEnter={e => (e.currentTarget.style.color='#F04438')}
            onMouseLeave={e => (e.currentTarget.style.color='#525870')}>
            {Icons.logOut} Déconnecter
          </button>
        </div>
        <div>© {new Date().getFullYear()} OCP Group</div>
      </div>
    </aside>
  )
}
