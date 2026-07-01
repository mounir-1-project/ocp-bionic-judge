import { useState, useMemo } from 'react'
import {
  ResponsiveContainer, ScatterChart, Scatter, XAxis, YAxis,
  CartesianGrid, Tooltip, PieChart, Pie, Cell,
} from 'recharts'
import { useApi }  from '../hooks/useApi.ts'
import { api }     from '../api.ts'
import { MACHINES, M_NAMES } from '../constants.ts'
import type { DecisionRecord, AuditLogEntry, GovernanceMetrics, DriftResult, AlertLevel } from '../types'
import {
  MetricCard, SkeletonCard, PageHeader, SectionHead,
  Alert, Spinner, ChartCard, StatusPill, Select,
} from '../components/UI.tsx'

const SEV_COLORS: Record<string, string> = {
  INFO:'#4F7CF6', WARNING:'#FFB020', CRITICAL:'#F04438',
}

const DownloadIcon = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
  </svg>
)

// ── DriftCard ─────────────────────────────────────────────────────────────────
interface DriftCardProps { drift: DriftResult | null; loading: boolean; error: string | null }
function DriftCard({ drift, loading, error }: DriftCardProps) {
  if (loading) return (
    <div style={{ borderRadius:14,padding:'18px 20px',background:'rgba(18,20,31,.98)',border:'1px solid rgba(37,40,64,.8)' }}>
      <div className="skeleton" style={{ height:9,width:'40%',marginBottom:12 }}/><div className="skeleton" style={{ height:20,width:'60%',marginBottom:8 }}/><div className="skeleton" style={{ height:8,width:'80%' }}/>
    </div>
  )
  if (error || !drift || drift.status === 'insufficient_data') return (
    <div style={{ borderRadius:14,padding:'16px 18px',background:'rgba(18,20,31,.98)',border:'1px solid rgba(37,40,64,.8)' }}>
      <div style={{ fontSize:9,fontWeight:800,color:'#525870',textTransform:'uppercase',letterSpacing:'1px',marginBottom:8 }}>Dérive modèle</div>
      <Alert msg={error ? `Indisponible : ${error}` : "Pas assez de données pour calculer la dérive."} kind={error?'warn':'info'}/>
    </div>
  )

  const { psi, ks_pvalue, drift_detected, alert_level, psi_threshold, ks_threshold } = drift
  const lvl = (alert_level ?? 'OK') as AlertLevel
  const levelColor = lvl==='CRITICAL'?'#F04438':lvl==='WARNING'?'#FFB020':'#00D37F'
  const levelRgb   = lvl==='CRITICAL'?'240,68,56':lvl==='WARNING'?'255,176,32':'0,211,127'

  return (
    <div style={{ borderRadius:14,padding:'18px 20px',position:'relative',overflow:'hidden', background:'linear-gradient(145deg,rgba(18,20,31,.98),rgba(13,15,24,.98))', border:`1px solid ${drift_detected?`rgba(${levelRgb},.35)`:'rgba(37,40,64,.8)'}`, boxShadow:drift_detected?`0 0 24px rgba(${levelRgb},.08)`:'none' }}>
      <div style={{ position:'absolute',top:0,left:0,right:0,height:'1px',background:`linear-gradient(90deg,transparent,rgba(${levelRgb},.7),transparent)` }}/>
      <div style={{ fontSize:9,fontWeight:800,color:'#525870',textTransform:'uppercase',letterSpacing:'1.2px',marginBottom:12 }}>Dérive modèle (PSI / KS)</div>
      <div style={{ display:'flex',alignItems:'center',gap:8,marginBottom:10 }}>
        <span style={{ fontSize:11,fontWeight:800,letterSpacing:'.5px',padding:'3px 10px',borderRadius:99, background:`rgba(${levelRgb},.1)`,border:`1px solid rgba(${levelRgb},.25)`,color:levelColor, display:'inline-flex',alignItems:'center',gap:5 }}>
          <span style={{ width:5,height:5,borderRadius:'50%',background:levelColor,animation:drift_detected?'pulse-dot 2.5s ease-in-out infinite':'none' }}/>
          {drift_detected ? `DÉRIVE DÉTECTÉE — ${lvl}` : 'STABLE'}
        </span>
      </div>
      {([
        { k:'PSI',      v:(psi??0).toFixed(4),            seuil:`seuil ${psi_threshold}`, warn:(psi??0)>(psi_threshold??0.2) },
        { k:'KS p-val', v:(ks_pvalue??0).toFixed(4),       seuil:`seuil ${ks_threshold}`, warn:(ks_pvalue??1)<(ks_threshold??0.05) },
        { k:'Réf.',     v:`${drift.reference_n} obs.`,     seuil:'historique', warn:false },
        { k:'Courant',  v:`${drift.current_n} obs.`,       seuil:'fenêtre',    warn:false },
      ] as Array<{k:string;v:string;seuil:string;warn:boolean}>).map(({ k,v,seuil,warn }) => (
        <div key={k} style={{ display:'flex',justifyContent:'space-between',alignItems:'center',padding:'3px 0',borderBottom:'1px solid rgba(37,40,64,.4)',fontSize:11 }}>
          <span style={{ color:'#525870' }}>{k}</span>
          <span style={{ color:warn?'#FFB020':'#C8CDD8',fontFamily:'JetBrains Mono,monospace',fontSize:10,fontWeight:600 }}>
            {v} <span style={{ color:'#3D4260',fontWeight:400 }}>({seuil})</span>
          </span>
        </div>
      ))}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function GovernancePage() {
  const [machineF, setMachineF] = useState('Toutes')
  const [sevF,     setSevF]     = useState('Toutes')
  const [typeF,    setTypeF]    = useState('Tous')

  const { data:gov,   loading:gLoad, error:gErr  } = useApi<GovernanceMetrics>(() => api.governance('24h'), [], 30_000)
  const { data:dec2,  error:dec2Err }               = useApi<DecisionRecord[]> (() => api.decisions({ limit:500 }), [], 30_000)
  const { data:audit, loading:aLoad, error:aErr  }  = useApi<AuditLogEntry[]>  (() => api.auditLog({ limit:500, machine_id:machineF!=='Toutes'?machineF:undefined, severity:sevF!=='Toutes'?sevF:undefined }), [machineF, sevF], 30_000)
  const { data:drift, loading:dLoad, error:dErr  }  = useApi<DriftResult>      (() => api.drift(), [], 60_000)

  const scatterData = useMemo(() => {
    if (!dec2) return []
    return dec2.slice(0, 600).map(d => ({ ts:new Date(d.timestamp).getTime(), score:d.anomaly_score??0, sev:d.severity }))
  }, [dec2])

  const filteredAudit = useMemo(() => (audit??[]).filter(r => typeF==='Tous' || r.event_type===typeF), [audit, typeF])

  const donutData = useMemo(() => {
    const map: Record<string, number> = {}
    filteredAudit.forEach(r => { map[r.severity] = (map[r.severity]??0) + 1 })
    return Object.entries(map).map(([name, value]) => ({ name, value }))
  }, [filteredAudit])

  const conf  = gov ? (gov.mean_judge_confidence??0)*100 : 0
  const disr  = gov ? (gov.disagreement_rate??0)*100    : 0
  const comp  = gov ? (gov.ocp_compliance_rate??0)*100  : 0
  const crit_ = gov ? (gov.critical_unresolved??0)      : 0

  function exportCSV() {
    if (!filteredAudit.length) return
    const keys = Object.keys(filteredAudit[0]) as Array<keyof AuditLogEntry>
    const rows = [keys.join(','), ...filteredAudit.map(r => keys.map(k => JSON.stringify(r[k]??'')).join(','))]
    const blob = new Blob([rows.join('\n')], { type:'text/csv' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `audit_ocp_${new Date().toISOString().slice(0,16).replace(/[:-]/g,'')}.csv`
    a.click()
  }

  const tooltipStyle = { background:'rgba(18,20,31,.98)',border:'1px solid rgba(53,58,82,.9)',borderRadius:10,fontSize:12 }

  return (
    <div className="animate-fade-up">
      <PageHeader title="Gouvernance & Audit" subtitle="Conformité ISO 55000 · Traçabilité complète · Surveillance dérive modèle" breadcrumb="Gouvernance & Audit" badge="Conformité"/>

      {gErr   && <Alert msg={`Métriques gouvernance indisponibles : ${gErr}`} kind="err"/>}
      {dec2Err && <Alert msg={`Décisions indisponibles : ${dec2Err}`} kind="warn"/>}

      {gLoad ? (
        <div style={{ display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:14,marginBottom:28 }}>
          {Array.from({length:4}).map((_,i) => <SkeletonCard key={i}/>)}
        </div>
      ) : gov && !gErr ? (
        <div style={{ display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:14,marginBottom:28 }}>
          <MetricCard value={`${conf.toFixed(1)} %`}  label="Confiance moyenne"    sub="Judge 24h"     color={conf>=70?'green':'amber'} icon="◎"/>
          <MetricCard value={`${disr.toFixed(1)} %`}  label="Taux de désaccord"    sub="Agent ↔ Judge" color={disr>30?'red':'green'}   icon="◆"/>
          <MetricCard value={`${comp.toFixed(1)} %`}  label="Conformité OCP"       sub="ISO 55000"     color={comp>=70?'green':'amber'} icon="◈"/>
          <MetricCard value={crit_}                   label="Critiques non résolus" sub="24 h"          color={crit_>0?'red':'green'}   icon="◉"/>
        </div>
      ) : null}

      {gov?.alerts?.map((a, i) => <Alert key={i} msg={a.message} kind="warn"/>)}

      <SectionHead>Dérive du modèle</SectionHead>
      <DriftCard drift={drift} loading={dLoad} error={dErr}/>

      {(dec2?.length ?? 0) > 0 && (
        <>
          <SectionHead>Distribution temporelle des anomalies</SectionHead>
          <ChartCard>
            <ResponsiveContainer width="100%" height={240}>
              <ScatterChart margin={{ top:8,right:8,bottom:4,left:0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(30,34,64,.9)"/>
                <XAxis type="number" dataKey="ts" domain={['auto','auto']} tickFormatter={(v: number) => new Date(v).toLocaleDateString('fr-FR',{day:'2-digit',month:'2-digit'})} tick={{ fontSize:9,fill:'#525870' }} stroke="rgba(37,40,64,.7)"/>
                <YAxis type="number" dataKey="score" domain={[0,1]} tick={{ fontSize:9,fill:'#525870' }} stroke="rgba(37,40,64,.7)" width={32}/>
                <Tooltip content={({ active, payload }) => {
                  if (!active || !payload?.length) return null
                  const d = payload[0].payload as { ts:number; score:number; sev:string }
                  return (
                    <div style={tooltipStyle}>
                      <div style={{ color:'#525870',marginBottom:4 }}>{new Date(d.ts).toLocaleString('fr-FR')}</div>
                      <div style={{ color:'#E8ECF1',fontWeight:600,marginBottom:4 }}>Score: {d.score.toFixed(4)}</div>
                      <StatusPill status={d.sev}/>
                    </div>
                  )
                }}/>
                {(['NORMAL','WARNING','CRITICAL'] as const).map(sev => (
                  <Scatter key={sev} name={sev} data={scatterData.filter(d => d.sev===sev)}
                    fill={sev==='NORMAL'?'#00D37F':sev==='WARNING'?'#FFB020':'#F04438'} opacity={0.65} r={3}/>
                ))}
              </ScatterChart>
            </ResponsiveContainer>
          </ChartCard>
        </>
      )}

      <SectionHead action={
        <button onClick={exportCSV} style={{ display:'inline-flex',alignItems:'center',gap:6,padding:'5px 13px',borderRadius:9,fontSize:11,fontWeight:600,cursor:'pointer', background:'rgba(18,20,31,.8)',border:'1px solid rgba(37,40,64,.8)',color:'#8B92A9',transition:'all .15s' }}
          onMouseEnter={e => { e.currentTarget.style.borderColor='rgba(0,211,127,.35)';e.currentTarget.style.color='#00D37F';e.currentTarget.style.background='rgba(0,211,127,.05)' }}
          onMouseLeave={e => { e.currentTarget.style.borderColor='rgba(37,40,64,.8)';e.currentTarget.style.color='#8B92A9';e.currentTarget.style.background='rgba(18,20,31,.8)' }}>
          <DownloadIcon/> Exporter CSV
        </button>
      }>Journal d'audit</SectionHead>

      {aErr && <Alert msg={`Journal d'audit indisponible : ${aErr}`} kind="err"/>}

      <div style={{ display:'grid',gridTemplateColumns:'1fr 1fr 1fr',gap:12,marginBottom:16 }}>
        <Select label="Machine"  value={machineF} onChange={setMachineF} options={[{v:'Toutes',l:'Toutes les machines'}, ...MACHINES.map(m => ({v:m,l:`${m} · ${M_NAMES[m]}`}))]}/>
        <Select label="Sévérité" value={sevF}     onChange={setSevF}     options={[{v:'Toutes',l:'Toutes'},{v:'INFO',l:'INFO'},{v:'WARNING',l:'WARNING'},{v:'CRITICAL',l:'CRITICAL'}]}/>
        <Select label="Type"     value={typeF}    onChange={setTypeF}    options={[{v:'Tous',l:'Tous'},{v:'JUDGE_EVALUATION',l:'JUDGE_EVALUATION'},{v:'DRIFT_CHECK',l:'DRIFT_CHECK'},{v:'PREDICTION',l:'PREDICTION'}]}/>
      </div>

      {aLoad ? <Spinner/> : !aErr && (
        <div style={{ display:'grid',gridTemplateColumns:'3fr 1fr',gap:14 }}>
          <div style={{ borderRadius:13,overflow:'hidden',border:'1px solid rgba(37,40,64,.7)',boxShadow:'0 4px 22px rgba(0,0,0,.2)' }}>
            {filteredAudit.length === 0
              ? <div style={{ padding:24 }}><Alert msg="Aucun log d'audit disponible." kind="info"/></div>
              : <div style={{ maxHeight:280,overflowY:'auto' }}>
                  <table style={{ width:'100%',borderCollapse:'collapse',fontSize:12 }}>
                    <thead style={{ position:'sticky',top:0,zIndex:1 }}>
                      <tr style={{ background:'rgba(22,24,36,.99)' }}>
                        {['Timestamp','Type','Machine','Action','Sévérité'].map(h => (
                          <th key={h} style={{ padding:'9px 13px',textAlign:'left',fontSize:9,fontWeight:800,color:'#525870',textTransform:'uppercase',letterSpacing:'.9px',borderBottom:'1px solid rgba(37,40,64,.8)',whiteSpace:'nowrap' }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {filteredAudit.slice(0,50).map((r, i) => (
                        <tr key={i} style={{ background:i%2===0?'rgba(18,20,31,.9)':'rgba(13,15,24,.9)',transition:'background .1s' }}
                          onMouseEnter={e => (e.currentTarget.style.background='rgba(26,28,42,.95)')}
                          onMouseLeave={e => (e.currentTarget.style.background=i%2===0?'rgba(18,20,31,.9)':'rgba(13,15,24,.9)')}>
                          <td style={{ padding:'7px 13px',borderBottom:'1px solid rgba(37,40,64,.4)',fontFamily:'JetBrains Mono,monospace',fontSize:10,color:'#8B92A9',whiteSpace:'nowrap' }}>{r.timestamp?.slice(0,19).replace('T',' ')}</td>
                          <td style={{ padding:'7px 13px',borderBottom:'1px solid rgba(37,40,64,.4)',color:'#C8CDD8',fontSize:11 }}>{r.event_type}</td>
                          <td style={{ padding:'7px 13px',borderBottom:'1px solid rgba(37,40,64,.4)',color:'#8B92A9',fontSize:11,fontFamily:'JetBrains Mono,monospace' }}>{r.machine_id}</td>
                          <td style={{ padding:'7px 13px',borderBottom:'1px solid rgba(37,40,64,.4)',color:'#C8CDD8',fontSize:11,maxWidth:170,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap' }}>{r.action}</td>
                          <td style={{ padding:'7px 13px',borderBottom:'1px solid rgba(37,40,64,.4)' }}><StatusPill status={r.severity}/></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
            }
          </div>
          <ChartCard title="Répartition">
            {donutData.length > 0 ? (
              <>
                <ResponsiveContainer width="100%" height={174}>
                  <PieChart>
                    <Pie data={donutData} cx="50%" cy="50%" innerRadius={44} outerRadius={70} dataKey="value" paddingAngle={3} strokeWidth={0}>
                      {donutData.map((d, i) => <Cell key={i} fill={SEV_COLORS[d.name]??'#525870'} stroke="#0C0E14" strokeWidth={2}/>)}
                    </Pie>
                    <Tooltip contentStyle={tooltipStyle}/>
                  </PieChart>
                </ResponsiveContainer>
                <div style={{ display:'flex',flexDirection:'column',gap:5,marginTop:6 }}>
                  {donutData.map(d => (
                    <div key={d.name} style={{ display:'flex',alignItems:'center',justifyContent:'space-between',fontSize:11 }}>
                      <span style={{ display:'flex',alignItems:'center',gap:6,color:'#8B92A9' }}>
                        <span style={{ width:7,height:7,borderRadius:2,background:SEV_COLORS[d.name]??'#525870',display:'inline-block' }}/>{d.name}
                      </span>
                      <span style={{ color:'#E8ECF1',fontWeight:700,fontFamily:'JetBrains Mono,monospace',fontSize:11 }}>{d.value}</span>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <div style={{ height:220,display:'flex',alignItems:'center',justifyContent:'center',color:'#525870',fontSize:12 }}>Pas de données</div>
            )}
          </ChartCard>
        </div>
      )}
    </div>
  )
}
