import { useState, useMemo, useEffect } from 'react'
import {
  ResponsiveContainer, ComposedChart, Line, Scatter, XAxis, YAxis,
  CartesianGrid, Tooltip, Legend, BarChart, Bar,
  type TooltipProps,
} from 'recharts'
import { useApi }  from '../hooks/useApi.ts'
import { api }     from '../api.ts'
import { MACHINES, M_NAMES, SENSORS, S_UNITS } from '../constants.ts'
import type { DecisionRecord, SensorReading, ChartPoint, SevByMachine, AnalyzeResponse } from '../types'
import {
  MetricCard, SkeletonCard, PageHeader, SectionHead,
  Alert, Gauge, Spinner, ChartCard, StatusPill, Select,
} from '../components/UI.tsx'

const PERIODS = [
  { v: 360,  l: '6 h'  },
  { v: 720,  l: '12 h' },
  { v: 1440, l: '24 h' },
] as const

const PlayIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><polygon points="5,3 19,12 5,21"/></svg>
)

function CustomTooltip({ active, payload, label, unit }: TooltipProps<number, string> & { unit?: string }) {
  if (!active || !payload?.length) return null
  return (
    <div style={{ background:'rgba(18,20,31,.98)',border:'1px solid rgba(53,58,82,.9)',borderRadius:10,padding:'9px 13px',fontSize:12,boxShadow:'0 8px 32px rgba(0,0,0,.4)' }}>
      <div style={{ color:'#525870',marginBottom:5,fontSize:11 }}>{new Date(label as string).toLocaleTimeString('fr-FR')}</div>
      {payload.map((p, i) => (
        <div key={i} style={{ color:(p.color as string)||'#E8ECF1',fontWeight:600 }}>
          {typeof p.value === 'number' ? p.value.toFixed(2) : p.value} {unit}
        </div>
      ))}
    </div>
  )
}

export default function SensorsPage() {
  const [machine, setMachine] = useState<string>(MACHINES[0])
  const [sensor,  setSensor]  = useState<string>(SENSORS[0])
  const [period,  setPeriod]  = useState<number>(720)

  const [useAgent,   setUseAgent]   = useState(true)
  const [runJudge,   setRunJudge]   = useState(true)
  const [analyzing,  setAnalyzing]  = useState(false)
  const [analyzeRes, setAnalyzeRes] = useState<AnalyzeResponse | null>(null)
  const [analyzeErr, setAnalyzeErr] = useState<string | null>(null)

  useEffect(() => {
    setAnalyzeRes(null)
    setAnalyzeErr(null)
  }, [machine])

  async function handleAnalyze() {
    setAnalyzing(true); setAnalyzeRes(null); setAnalyzeErr(null)
    try {
      setAnalyzeRes(await api.analyze(machine, useAgent, runJudge))
    } catch (e) {
      setAnalyzeErr(e instanceof Error ? e.message : 'Erreur inconnue')
    } finally {
      setAnalyzing(false)
    }
  }

  const { data: decAll,     error: decAllErr } = useApi<DecisionRecord[]>(() => api.decisions({ limit:500 }), [], 30_000)
  const { data: sensorData, loading: sLoad, error: sErr } = useApi<SensorReading[]>(() => api.sensors(machine, period), [machine, period], 30_000)
  const { data: decMachine } = useApi<DecisionRecord[]>(() => api.decisions({ machine_id:machine, limit:500 }), [machine, period], 30_000)

  const stats = useMemo(() => {
    if (!decAll) return { total:0,machines:0,anomalies:0,critical:0,normal:0 }
    return {
      total:    decAll.length,
      machines: new Set(decAll.map(d => d.machine_id)).size,
      anomalies: decAll.filter(d => d.is_anomaly).length,
      critical:  decAll.filter(d => d.severity === 'CRITICAL').length,
      normal:    decAll.filter(d => d.severity === 'NORMAL').length,
    }
  }, [decAll])

  const chartData = useMemo((): ChartPoint[] => {
    if (!sensorData?.length) return []
    const decMap: Record<string, DecisionRecord> = {}
    decMachine?.forEach(d => {
      if (!d.timestamp) return
      const key = d.timestamp.replace(/[Z+].*$/, '').slice(0, 19)
      decMap[key] = d
    })
    return sensorData.map(r => {
      const key = (r.timestamp ?? '').replace(/[Z+].*$/, '').slice(0, 19)
      const dec = decMap[key]
      return { ts:r.timestamp, value:(r as unknown as Record<string,number>)[sensor]??0, sev:dec?.severity??'NORMAL', score:dec?.anomaly_score??0 }
    })
  }, [sensorData, decMachine, sensor])

  const latest = chartData[chartData.length - 1]

  const sevByMachine = useMemo((): SevByMachine[] => {
    if (!decAll) return []
    const map: Record<string, SevByMachine> = Object.fromEntries(MACHINES.map(m => [m, { machine:m,NORMAL:0,WARNING:0,CRITICAL:0 }]))
    decAll.forEach(d => { if (map[d.machine_id]) map[d.machine_id][d.severity]++ })
    return Object.values(map)
  }, [decAll])

  const critAlerts = useMemo(() => (decAll ?? []).filter(d => d.severity === 'CRITICAL').slice(0, 20), [decAll])
  const pct = stats.total ? `${(stats.anomalies / stats.total * 100).toFixed(1)} %` : '—'

  return (
    <div className="animate-fade-up">
      <PageHeader title="Surveillance Capteurs" subtitle="Détection d'anomalies en temps réel · 5 machines · OCP" breadcrumb="Capteurs & Détection" badge="Sync 30s"/>

      {decAllErr && <Alert msg={`Impossible de charger les décisions : ${decAllErr}`} kind="err"/>}

      {!decAll && !decAllErr ? (
        <div style={{ display:'grid',gridTemplateColumns:'repeat(5,1fr)',gap:14,marginBottom:28 }}>
          {Array.from({ length:5 }).map((_,i) => <SkeletonCard key={i}/>)}
        </div>
      ) : (
        <div style={{ display:'grid',gridTemplateColumns:'repeat(5,1fr)',gap:14,marginBottom:28 }}>
          <MetricCard value={stats.machines}                     label="Machines actives"   sub="sites OCP"          color="teal"  icon="▣"/>
          <MetricCard value={stats.total.toLocaleString()}        label="Lectures analysées" sub="par le modèle ML"    color="blue"  icon="◈"/>
          <MetricCard value={stats.anomalies.toLocaleString()}    label="Anomalies"          sub={pct}                color="amber" icon="◆"/>
          <MetricCard value={stats.critical.toLocaleString()}     label="Alertes critiques"  sub="intervention req."  color="red"   icon="◉"/>
          <MetricCard value={stats.normal.toLocaleString()}       label="Lectures normales"  sub="fonctionnement OK"  color="green" icon="◎"/>
        </div>
      )}

      <div style={{ display:'grid',gridTemplateColumns:'2fr 2fr 1fr',gap:12,marginBottom:16 }}>
        <Select label="Machine" value={machine} onChange={setMachine} options={MACHINES.map(m => ({ v:m, l:`${m}  ·  ${M_NAMES[m]}` }))}/>
        <Select label="Capteur" value={sensor}  onChange={setSensor}  options={SENSORS.map(s => ({ v:s, l:`${s.charAt(0).toUpperCase()+s.slice(1)}  (${S_UNITS[s as keyof typeof S_UNITS]})` }))}/>
        <Select label="Période" value={period}  onChange={v => setPeriod(Number(v))} options={PERIODS.map(p => ({ v:p.v, l:p.l }))}/>
      </div>

      {/* Analyze panel */}
      <div style={{ display:'flex',alignItems:'center',justifyContent:'space-between',flexWrap:'wrap',gap:12,padding:'14px 18px',marginBottom:18,borderRadius:12,background:'rgba(13,15,24,.8)',border:'1px solid rgba(37,40,64,.7)',boxShadow:'inset 0 1px 0 rgba(255,255,255,.03)' }}>
        <div style={{ display:'flex',alignItems:'center',gap:14 }}>
          <span style={{ fontSize:11,fontWeight:700,color:'#6B7280',textTransform:'uppercase',letterSpacing:'1px' }}>Lancer l'analyse</span>
          {([{ label:'Agent IA',checked:useAgent,set:setUseAgent },{ label:'Judge eval.',checked:runJudge,set:setRunJudge }] as Array<{ label:string;checked:boolean;set:(v:boolean)=>void }>).map(({ label,checked,set }) => (
            <label key={label} style={{ display:'flex',alignItems:'center',gap:6,cursor:'pointer',fontSize:12,color:'#8B92A9',userSelect:'none' }}>
              <span style={{ width:14,height:14,borderRadius:4,flexShrink:0,background:checked?'rgba(0,211,127,.8)':'rgba(37,40,64,.9)',border:`1px solid ${checked?'rgba(0,211,127,.5)':'rgba(37,40,64,.9)'}`,display:'flex',alignItems:'center',justifyContent:'center',transition:'all .15s' }} onClick={() => set(!checked)}>
                {checked && <span style={{ color:'#0C0E14',fontSize:10,fontWeight:900,lineHeight:1 }}>✓</span>}
              </span>
              {label}
            </label>
          ))}
        </div>
        <button onClick={handleAnalyze} disabled={analyzing} style={{ display:'inline-flex',alignItems:'center',gap:8,padding:'9px 20px',borderRadius:10,border:'none',cursor:analyzing?'not-allowed':'pointer', background:analyzing?'rgba(0,163,98,.35)':'linear-gradient(135deg,rgba(0,211,127,.88),rgba(0,163,98,.88))', color:'#0C0E14',fontSize:12,fontWeight:800,letterSpacing:'.3px', boxShadow:analyzing?'none':'0 4px 22px rgba(0,211,127,.28)',transition:'all .2s cubic-bezier(.34,1.56,.64,1)',opacity:analyzing?.7:1 }}
          onMouseEnter={e => { if(!analyzing){e.currentTarget.style.transform='translateY(-1px)';e.currentTarget.style.boxShadow='0 7px 28px rgba(0,211,127,.38)'}}}
          onMouseLeave={e => { e.currentTarget.style.transform='translateY(0)';e.currentTarget.style.boxShadow=analyzing?'none':'0 4px 22px rgba(0,211,127,.28)' }}>
          {analyzing ? <><div style={{ width:12,height:12,borderRadius:'50%',border:'2px solid rgba(12,14,20,.3)',borderTopColor:'#0C0E14',animation:'spin .7s linear infinite' }}/>Analyse en cours…</> : <><PlayIcon/> Analyser {machine}</>}
          <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
        </button>
      </div>

      {analyzeErr && <Alert msg={`Analyse échouée : ${analyzeErr}`} kind="err"/>}
      {analyzeRes && (
        <Alert kind="ok" msg={`
          <strong>${analyzeRes.machine_id}</strong> — Score : <strong>${(analyzeRes.anomaly_score*100).toFixed(1)}%</strong>
          · Sévérité : <strong>${analyzeRes.severity}</strong>
          ${analyzeRes.judge_score != null ? `· Judge : <strong>${analyzeRes.judge_score.toFixed(1)}/10</strong>` : ''}
          ${analyzeRes.diagnosis ? `<br/><span style="opacity:.85">${analyzeRes.diagnosis}</span>` : ''}
          <span style="opacity:.5;font-size:10px;margin-left:8px">${analyzeRes.processing_ms.toFixed(0)} ms</span>
        `}/>
      )}

      {sErr && <Alert msg={`Erreur capteur : ${sErr}`} kind="err"/>}
      {!sErr && (sLoad ? <Spinner/> : chartData.length === 0 ? (
        <Alert msg="Aucune donnée disponible pour cette machine." kind="info"/>
      ) : (
        <div style={{ display:'grid',gridTemplateColumns:'4fr 1fr',gap:14,marginBottom:8 }}>
          <ChartCard title={`${M_NAMES[machine as keyof typeof M_NAMES]} · ${sensor.charAt(0).toUpperCase()+sensor.slice(1)} (${S_UNITS[sensor as keyof typeof S_UNITS]})`}>
            <ResponsiveContainer width="100%" height={280}>
              <ComposedChart data={chartData} margin={{ top:8,right:8,bottom:4,left:0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(30,34,64,.9)"/>
                <XAxis dataKey="ts" tickFormatter={(v: string) => new Date(v).toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'})} tick={{ fontSize:9,fill:'#525870' }} stroke="rgba(37,40,64,.7)" interval="preserveStartEnd"/>
                <YAxis tick={{ fontSize:9,fill:'#525870' }} stroke="rgba(37,40,64,.7)" width={40}/>
                <Tooltip content={<CustomTooltip unit={S_UNITS[sensor as keyof typeof S_UNITS]}/>}/>
                <Line dataKey="value" type="monotone" stroke="#00D37F" strokeWidth={1.8} dot={false}/>
                <Scatter data={chartData.filter(d => d.sev==='WARNING')}  dataKey="value" fill="#FFB020" shape="diamond"/>
                <Scatter data={chartData.filter(d => d.sev==='CRITICAL')} dataKey="value" fill="#F04438" shape="cross"/>
              </ComposedChart>
            </ResponsiveContainer>
          </ChartCard>
          <ChartCard>
            <div style={{ height:280,display:'flex',alignItems:'center',justifyContent:'center' }}>
              <Gauge score={latest?.score??0} severity={latest?.sev??'NORMAL'}/>
            </div>
          </ChartCard>
        </div>
      ))}

      <SectionHead>Sévérités par machine</SectionHead>
      <ChartCard>
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={sevByMachine} margin={{ top:8,right:8,bottom:4,left:0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(30,34,64,.9)"/>
            <XAxis dataKey="machine" tick={{ fontSize:9,fill:'#525870' }} stroke="rgba(37,40,64,.7)"/>
            <YAxis tick={{ fontSize:9,fill:'#525870' }} stroke="rgba(37,40,64,.7)" width={36}/>
            <Tooltip contentStyle={{ background:'rgba(18,20,31,.98)',border:'1px solid rgba(53,58,82,.9)',borderRadius:10,fontSize:12 }} labelStyle={{ color:'#8B92A9' }}/>
            <Legend wrapperStyle={{ fontSize:10,color:'#8B92A9',paddingTop:4 }}/>
            <Bar dataKey="NORMAL"   stackId="a" fill="#00D37F" radius={[0,0,0,0] as [number,number,number,number]}/>
            <Bar dataKey="WARNING"  stackId="a" fill="#FFB020"/>
            <Bar dataKey="CRITICAL" stackId="a" fill="#F04438" radius={[4,4,0,0] as [number,number,number,number]}/>
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>

      <SectionHead>Alertes critiques récentes</SectionHead>
      {critAlerts.length === 0 ? (
        <Alert msg="Aucune alerte critique enregistrée." kind="ok"/>
      ) : (
        <div style={{ borderRadius:13,overflow:'hidden',border:'1px solid rgba(37,40,64,.7)',boxShadow:'0 4px 22px rgba(0,0,0,.22)' }}>
          <table style={{ width:'100%',borderCollapse:'collapse',fontSize:12 }}>
            <thead>
              <tr style={{ background:'rgba(30,33,50,.98)' }}>
                {['Machine','Timestamp','Score','Sévérité','Modèle'].map(h => (
                  <th key={h} style={{ padding:'10px 14px',textAlign:'left',fontSize:9,fontWeight:800,color:'#525870',textTransform:'uppercase',letterSpacing:'.9px',borderBottom:'1px solid rgba(37,40,64,.8)' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {critAlerts.map((d, i) => (
                <tr key={i} style={{ background:i%2===0?'rgba(20,22,34,.9)':'rgba(14,16,26,.9)',transition:'background .12s' }}
                  onMouseEnter={e => (e.currentTarget.style.background='rgba(30,33,50,.95)')}
                  onMouseLeave={e => (e.currentTarget.style.background=i%2===0?'rgba(20,22,34,.9)':'rgba(14,16,26,.9)')}>
                  <td style={{ padding:'8px 14px',borderBottom:'1px solid rgba(37,40,64,.45)',color:'#C8CDD8',fontFamily:'JetBrains Mono,monospace',fontSize:11 }}>{d.machine_id}</td>
                  <td style={{ padding:'8px 14px',borderBottom:'1px solid rgba(37,40,64,.45)',color:'#8B92A9',fontFamily:'JetBrains Mono,monospace',fontSize:10 }}>{d.timestamp?.slice(0,19).replace('T',' ')}</td>
                  <td style={{ padding:'8px 14px',borderBottom:'1px solid rgba(37,40,64,.45)' }}>
                    <div style={{ display:'flex',alignItems:'center',gap:7 }}>
                      <div style={{ height:4,background:'rgba(37,40,64,.9)',borderRadius:2,width:64,overflow:'hidden' }}>
                        <div style={{ height:'100%',width:`${(d.anomaly_score)*100}%`,background:'#F04438',borderRadius:2 }}/>
                      </div>
                      <span style={{ fontSize:10,color:'#8B92A9',fontFamily:'JetBrains Mono,monospace' }}>{(d.anomaly_score*100).toFixed(1)}%</span>
                    </div>
                  </td>
                  <td style={{ padding:'8px 14px',borderBottom:'1px solid rgba(37,40,64,.45)' }}><StatusPill status={d.severity}/></td>
                  <td style={{ padding:'8px 14px',borderBottom:'1px solid rgba(37,40,64,.45)',color:'#6B7280',fontFamily:'JetBrains Mono,monospace',fontSize:10 }}>{d.model_version??'—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
