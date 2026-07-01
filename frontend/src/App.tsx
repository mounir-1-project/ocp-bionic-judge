import { useState, useEffect } from 'react'
import { login, logout, checkAuth, setAuthErrorHandler } from './api.ts'
import Sidebar        from './components/Sidebar.tsx'
import ErrorBoundary  from './components/ErrorBoundary.tsx'
import SensorsPage    from './pages/SensorsPage.tsx'
import JudgePage      from './pages/JudgePage.tsx'
import GovernancePage from './pages/GovernancePage.tsx'
import { ToastProvider } from './components/UI.tsx'

type PageId = 'sensors' | 'judge' | 'governance'

// ── Eye icon ──────────────────────────────────────────────────────────────────
function EyeIcon({ open }: { open: boolean }) {
  return open ? (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>
    </svg>
  ) : (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/>
      <line x1="1" y1="1" x2="23" y2="23"/>
    </svg>
  )
}

// ── Animated background ───────────────────────────────────────────────────────
function AnimatedBg() {
  return (
    <div style={{ position:'fixed',inset:0,overflow:'hidden',pointerEvents:'none' }}>
      <div style={{ position:'absolute',inset:0,backgroundImage:'radial-gradient(circle,rgba(30,34,64,.85) 1px,transparent 1px)',backgroundSize:'28px 28px' }}/>
      <div style={{ position:'absolute',top:'50%',left:'50%',transform:'translate(-50%,-55%)',width:700,height:700,borderRadius:'50%',background:'radial-gradient(circle,rgba(0,211,127,.04) 0%,transparent 65%)' }}/>
      <div style={{ position:'absolute',top:-120,right:-120,width:440,height:440,borderRadius:'50%',background:'radial-gradient(circle,rgba(79,124,246,.05) 0%,transparent 70%)' }}/>
      <div style={{ position:'absolute',left:0,right:0,height:'1px',background:'linear-gradient(90deg,transparent,rgba(0,211,127,.12),transparent)',animation:'scan-line 8s ease-in-out infinite' }}/>
    </div>
  )
}

// ── Login screen ──────────────────────────────────────────────────────────────
function KeyScreen({ onSuccess }: { onSuccess: () => void }) {
  const [val,      setVal]      = useState('')
  const [err,      setErr]      = useState('')
  const [loading,  setLoading]  = useState(false)
  const [showPass, setShowPass] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!val.trim()) { setErr('Entrez une clé API.'); return }
    setLoading(true); setErr('')
    try {
      await login(val.trim())
      onSuccess()
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "Impossible de joindre l'API.")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ minHeight:'100vh',display:'flex',alignItems:'center',justifyContent:'center',position:'relative' }}>
      <AnimatedBg/>
      <div className="animate-scale-in" style={{ position:'relative',zIndex:1,width:428,padding:'38px 36px 30px', background:'linear-gradient(145deg,rgba(17,19,30,.98) 0%,rgba(13,15,24,.98) 100%)', borderRadius:22,border:'1px solid rgba(37,40,64,.75)', boxShadow:'0 36px 100px rgba(0,0,0,.65),0 0 0 1px rgba(0,211,127,.03),inset 0 1px 0 rgba(255,255,255,.035)' }}>
        <div style={{ position:'absolute',top:0,left:0,right:0,height:'1px',borderRadius:'22px 22px 0 0',background:'linear-gradient(90deg,transparent 5%,rgba(0,211,127,.55) 50%,transparent 95%)' }}/>

        {/* Logo */}
        <div style={{ display:'flex',alignItems:'center',gap:14,marginBottom:26 }}>
          <div style={{ width:52,height:52,borderRadius:15,flexShrink:0, background:'linear-gradient(135deg,rgba(0,211,127,.14) 0%,rgba(0,211,127,.04) 100%)', border:'1px solid rgba(0,211,127,.22)', display:'flex',alignItems:'center',justifyContent:'center',position:'relative',overflow:'hidden', boxShadow:'0 0 28px rgba(0,211,127,.14),inset 0 1px 0 rgba(0,211,127,.1)', padding:6 }}>
            <img src="/ocp_logo.png" alt="OCP"
              style={{ width:'100%',height:'100%',objectFit:'contain' }}
              onError={e => { (e.target as HTMLImageElement).style.display='none'; (e.target as HTMLImageElement).parentElement!.innerHTML='⚗️' }}/>
          </div>
          <div>
            <div style={{ fontSize:21,fontWeight:900,color:'#E8ECF1',letterSpacing:'-0.6px',lineHeight:1.1 }}>OCP Bionic Judge</div>
            <div style={{ fontSize:9.5,color:'#525870',textTransform:'uppercase',letterSpacing:'1.5px',marginTop:5,display:'flex',alignItems:'center',gap:6 }}>
              <span style={{ width:5,height:5,background:'#00D37F',borderRadius:'50%',boxShadow:'0 0 8px rgba(0,211,127,.7)',animation:'pulse-dot 2.5s ease-in-out infinite' }}/>
              Industrial AI Platform
            </div>
          </div>
        </div>

        <div style={{ height:1,marginBottom:22,background:'linear-gradient(90deg,transparent,rgba(37,40,64,.8),transparent)' }}/>
        <p style={{ fontSize:12,color:'#525870',marginBottom:22,lineHeight:1.75,margin:'0 0 22px' }}>
          Entrez votre clé API pour ouvrir une session sécurisée. La clé est validée côté serveur — jamais stockée dans le navigateur.
        </p>

        <form onSubmit={handleSubmit}>
          <label style={{ fontSize:9,fontWeight:800,color:'#525870',textTransform:'uppercase',letterSpacing:'1.3px',display:'block',marginBottom:7 }}>Clé API</label>
          <div style={{ position:'relative',marginBottom:14 }}>
            <input type={showPass?'text':'password'} value={val} onChange={e => { setVal(e.target.value); setErr('') }}
              placeholder="ocp-bionic-dev-key" autoFocus disabled={loading}
              style={{ width:'100%',padding:'11px 42px 11px 14px',background:'rgba(9,11,20,.85)', border:`1px solid ${err?'rgba(240,68,56,.45)':'rgba(37,40,64,.8)'}`,borderRadius:11,color:'#E8ECF1',fontSize:13, fontFamily:'JetBrains Mono,monospace',outline:'none',transition:'border-color .15s, box-shadow .15s',opacity:loading?.55:1 }}
              onFocus={e => { e.target.style.borderColor='rgba(0,211,127,.45)'; e.target.style.boxShadow='0 0 0 3px rgba(0,211,127,.07),inset 0 1px 0 rgba(0,0,0,.2)' }}
              onBlur={e  => { e.target.style.borderColor=err?'rgba(240,68,56,.45)':'rgba(37,40,64,.8)'; e.target.style.boxShadow='none' }}/>
            <button type="button" tabIndex={-1} onClick={() => setShowPass(v => !v)}
              style={{ position:'absolute',right:12,top:'50%',transform:'translateY(-50%)',background:'none',border:'none',cursor:'pointer',padding:2,color:'#525870',display:'flex',alignItems:'center',transition:'color .15s' }}
              onMouseEnter={e => (e.currentTarget.style.color='#8B92A9')}
              onMouseLeave={e => (e.currentTarget.style.color='#525870')}>
              <EyeIcon open={showPass}/>
            </button>
          </div>

          {err && (
            <div style={{ display:'flex',alignItems:'center',gap:8,marginBottom:14,fontSize:12,color:'#F87171', padding:'8px 12px',background:'rgba(240,68,56,.06)',borderRadius:9,border:'1px solid rgba(240,68,56,.18)' }}>
              <span>✕</span> {err}
            </div>
          )}

          <button type="submit" disabled={loading} style={{
            width:'100%',padding:'12px',borderRadius:11,border:'1px solid rgba(0,211,127,.2)',
            background:loading?'rgba(0,163,98,.35)':'linear-gradient(135deg,rgba(0,211,127,.92) 0%,rgba(0,163,98,.92) 100%)',
            cursor:loading?'not-allowed':'pointer',color:'#0C0E14',fontSize:13,fontWeight:800,letterSpacing:'.3px',
            boxShadow:loading?'none':'0 4px 28px rgba(0,211,127,.32),inset 0 1px 0 rgba(255,255,255,.18)',
            transition:'all .2s cubic-bezier(.34,1.56,.64,1)',display:'flex',alignItems:'center',justifyContent:'center',gap:8,
          }}
            onMouseEnter={e => { if(!loading){e.currentTarget.style.transform='translateY(-2px)';e.currentTarget.style.boxShadow='0 8px 36px rgba(0,211,127,.42),inset 0 1px 0 rgba(255,255,255,.18)'}}}
            onMouseLeave={e => { e.currentTarget.style.transform='translateY(0)';e.currentTarget.style.boxShadow=loading?'none':'0 4px 28px rgba(0,211,127,.32),inset 0 1px 0 rgba(255,255,255,.18)' }}>
            {loading && <div style={{ width:14,height:14,borderRadius:'50%',border:'2px solid rgba(12,14,20,.25)',borderTopColor:'#0C0E14',animation:'spin .7s linear infinite',flexShrink:0 }}/>}
            {loading ? 'Connexion en cours…' : 'Accéder au tableau de bord →'}
            <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
          </button>
        </form>

        <div style={{ marginTop:18,fontSize:10,color:'#3D4260',textAlign:'center',lineHeight:1.9,display:'flex',alignItems:'center',justifyContent:'center',gap:6 }}>
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
          Session sécurisée via cookie httpOnly · 8 heures
        </div>
      </div>
    </div>
  )
}

// ─── App shell ────────────────────────────────────────────────────────────────
export default function App() {
  const [authenticated, setAuthenticated] = useState(false)
  const [authChecked,   setAuthChecked]   = useState(false)
  const [page,          setPage]          = useState<PageId>('sensors')

  // On page reload: verify existing cookie before showing login screen
  useEffect(() => {
    checkAuth().then(ok => {
      setAuthenticated(ok)
      setAuthChecked(true)
    })
  }, [])

  useEffect(() => {
    setAuthErrorHandler(async () => {
      await logout().catch(() => {})
      setAuthenticated(false)
    })
    return () => setAuthErrorHandler(null)
  }, [])

  // Blank screen while checking session — avoids login flash
  if (!authChecked) return null

  async function handleLogout() {
    await logout()
    setAuthenticated(false)
  }

  if (!authenticated) return <KeyScreen onSuccess={() => setAuthenticated(true)}/>

  return (
    <ToastProvider>
      <div style={{ display:'flex',height:'100vh',overflow:'hidden' }}>
        <Sidebar page={page} onPage={setPage} onLogout={handleLogout}/>
        <main style={{ flex:1,overflowY:'auto',padding:'0 32px 48px', background:'#0C0E14',backgroundImage:'radial-gradient(circle,rgba(30,34,64,.8) 1px,transparent 1px)',backgroundSize:'28px 28px' }}>
          <ErrorBoundary>
            {page === 'sensors'    && <SensorsPage/>}
            {page === 'judge'      && <JudgePage/>}
            {page === 'governance' && <GovernancePage/>}
          </ErrorBoundary>
        </main>
      </div>
    </ToastProvider>
  )
}
