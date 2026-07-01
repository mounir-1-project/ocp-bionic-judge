import { useMemo } from 'react'
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ReferenceLine, LineChart, Line, Legend,
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
} from 'recharts'
import { useApi }  from '../hooks/useApi.ts'
import { api }     from '../api.ts'
import type { JudgeEvaluation } from '../types'
import {
  MetricCard, SkeletonCard, PageHeader, SectionHead,
  Alert, Spinner, ChartCard,
} from '../components/UI.tsx'

const CRITERIA: Record<string, string> = {
  relevance_score:   'Pertinence (25%)',
  history_score:     'Historique (20%)',
  confidence_score:  'Confiance (20%)',
  compliance_score:  'Conformité (20%)',
  feasibility_score: 'Faisabilité (15%)',
}
const LINE_COLORS = ['#00D37F','#FFB020','#4F7CF6','#A78BFA','#06B6D4']

function heatColor(v: number): { bg: string; text: string } {
  if (v >= 7.5) return { bg:'rgba(0,211,127,.65)',  text:'#042A1C' }
  if (v >= 5.5) return { bg:'rgba(255,176,32,.6)',  text:'#2A1E00' }
  return                { bg:'rgba(240,68,56,.58)', text:'#2A0A08' }
}

interface HeatmapRow { machine: string; [key: string]: string | number }
interface RadarPoint  { criterion: string; value: number }
interface HistoPoint  { range: string; n: number }
interface TimePoint   { machine_id: string; timestamp: string; global_score: number }

export default function JudgePage() {
  const { data: ev, loading, error } = useApi<JudgeEvaluation[]>(() => api.judgeEvals(500), [], 30_000)

  const stats = useMemo(() => {
    if (!ev?.length) return null
    const ms = ev.reduce((s, e) => s + (e.global_score ?? 0), 0) / ev.length
    const ar = ev.reduce((s, e) => s + (e.agreement ? 1 : 0), 0) / ev.length * 100
    const nd = ev.filter(e => !e.agreement || e.global_score < 6).length
    return { total:ev.length, ms, ar, nd }
  }, [ev])

  const histogram = useMemo((): HistoPoint[] => {
    if (!ev?.length) return []
    const bins: HistoPoint[] = Array.from({ length:20 }, (_,i) => ({ range:`${(i*0.5).toFixed(1)}`, n:0 }))
    ev.forEach(e => { bins[Math.min(Math.floor((e.global_score??0)*2), 19)].n++ })
    return bins
  }, [ev])

  const radarData = useMemo((): RadarPoint[] => {
    if (!ev?.length) return []
    const keys = Object.keys(CRITERIA).filter(k => (ev[0] as unknown as Record<string,unknown>)?.[k] != null)
    return keys.map(k => ({
      criterion: CRITERIA[k],
      value: +(ev.reduce((s, e) => s + ((e as unknown as Record<string,number>)[k]??0), 0) / ev.length).toFixed(2),
    }))
  }, [ev])

  const timeData = useMemo(() => {
    if (!ev?.length) return { machines: [] as string[], series: [] as TimePoint[] }
    const sorted = [...ev].sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())
    const machines = [...new Set(sorted.map(e => e.machine_id).filter(Boolean))]
    return { machines, series: sorted as unknown as TimePoint[] }
  }, [ev])

  const heatmap = useMemo((): HeatmapRow[] => {
    if (!ev?.length) return []
    const keys = Object.keys(CRITERIA).filter(k => (ev[0] as unknown as Record<string,unknown>)?.[k] != null)
    const machines = [...new Set(ev.map(e => e.machine_id).filter(Boolean))]
    return machines.map(m => {
      const rows = ev.filter(e => e.machine_id === m)
      const entry: HeatmapRow = { machine:m }
      keys.forEach(k => {
        entry[CRITERIA[k]] = +(rows.reduce((s,e) => s + ((e as unknown as Record<string,number>)[k]??0),0) / rows.length).toFixed(2)
      })
      return entry
    })
  }, [ev])

  const tooltipStyle = { background:'rgba(18,20,31,.98)',border:'1px solid rgba(53,58,82,.9)',borderRadius:10,fontSize:12 }

  if (loading) return (
    <>
      <PageHeader title="Judge Agent" subtitle="Chargement…" breadcrumb="Judge Agent"/>
      <div style={{ display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:14,marginBottom:28 }}>
        {Array.from({length:4}).map((_,i) => <SkeletonCard key={i}/>)}
      </div>
      <Spinner/>
    </>
  )
  if (error) return (
    <>
      <PageHeader title="Judge Agent" subtitle="Erreur de chargement" breadcrumb="Judge Agent"/>
      <Alert msg={`Impossible de charger les évaluations : ${error}`} kind="err"/>
    </>
  )

  return (
    <div className="animate-fade-up">
      <PageHeader title="Judge Agent" subtitle="Évaluation indépendante des décisions IA · 5 critères pondérés · Google Gemini 2.0 Flash" breadcrumb="Judge Agent" badge="Gouvernance IA"/>

      {!ev?.length ? (
        <Alert msg="Aucune évaluation disponible. Lancez <code>POST /analyze</code> avec <code>run_judge: true</code>." kind="info"/>
      ) : (
        <>
          {stats && (
            <div style={{ display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:14,marginBottom:28 }}>
              <MetricCard value={stats.total}                    label="Évaluations"   sub="enregistrées"  color="blue"  icon="◈"/>
              <MetricCard value={`${stats.ms.toFixed(1)}/10`}    label="Score moyen"   sub="Judge global"  color={stats.ms>=6?'green':'amber'} icon="◎"/>
              <MetricCard value={`${stats.ar.toFixed(0)} %`}     label="Taux d'accord" sub="Agent ↔ Judge" color={stats.ar>=70?'green':'amber'} icon="◆"/>
              <MetricCard value={stats.nd}                       label="Désaccords"    sub="score < 6.0"   color={stats.nd>0?'red':'green'} icon="◉"/>
            </div>
          )}

          <div style={{ display:'grid',gridTemplateColumns:'1fr 1fr',gap:14,marginBottom:8 }}>
            <div>
              <SectionHead>Distribution des scores</SectionHead>
              <ChartCard>
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart data={histogram} margin={{ top:8,right:8,bottom:4,left:0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(30,34,64,.9)"/>
                    <XAxis dataKey="range" tick={{ fontSize:9,fill:'#525870' }} stroke="rgba(37,40,64,.7)" interval={3}/>
                    <YAxis tick={{ fontSize:9,fill:'#525870' }} stroke="rgba(37,40,64,.7)" width={32}/>
                    <Tooltip contentStyle={tooltipStyle}/>
                    <ReferenceLine x="6.0" stroke="#F04438" strokeDasharray="4 2" strokeWidth={1.5} label={{ value:'6.0',fill:'#F04438',fontSize:9,position:'insideTopRight' }}/>
                    <Bar dataKey="n" fill="#00D37F" opacity={0.75} radius={[4,4,0,0] as [number,number,number,number]}/>
                  </BarChart>
                </ResponsiveContainer>
              </ChartCard>
            </div>
            <div>
              <SectionHead>Profil multi-critères</SectionHead>
              <ChartCard>
                <ResponsiveContainer width="100%" height={260}>
                  <RadarChart data={radarData} margin={{ top:10,right:30,bottom:10,left:30 }}>
                    <PolarGrid stroke="rgba(37,40,64,.8)"/>
                    <PolarAngleAxis dataKey="criterion" tick={{ fontSize:9,fill:'#8B92A9' }}/>
                    <PolarRadiusAxis angle={30} domain={[0,10]} tick={{ fontSize:8,fill:'#525870' }}/>
                    <Radar dataKey="value" stroke="#00D37F" fill="#00D37F" fillOpacity={0.07} dot={{ fill:'#00D37F',r:4 }} strokeWidth={1.8}/>
                    <Tooltip contentStyle={tooltipStyle}/>
                  </RadarChart>
                </ResponsiveContainer>
              </ChartCard>
            </div>
          </div>

          <SectionHead>Évolution temporelle des scores</SectionHead>
          <ChartCard>
            <ResponsiveContainer width="100%" height={240}>
              <LineChart data={timeData.series} margin={{ top:8,right:8,bottom:4,left:0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(30,34,64,.9)"/>
                <XAxis dataKey="timestamp" tickFormatter={(v: string) => new Date(v).toLocaleDateString('fr-FR',{day:'2-digit',month:'2-digit'})} tick={{ fontSize:9,fill:'#525870' }} stroke="rgba(37,40,64,.7)" interval="preserveStartEnd"/>
                <YAxis domain={[0,10.5]} tick={{ fontSize:9,fill:'#525870' }} stroke="rgba(37,40,64,.7)" width={30}/>
                <Tooltip contentStyle={tooltipStyle}/>
                <ReferenceLine y={6} stroke="#F04438" strokeDasharray="4 2" strokeWidth={1} label={{ value:'Seuil 6.0',fill:'#F04438',fontSize:9,position:'insideTopRight' }}/>
                <Legend wrapperStyle={{ fontSize:10,color:'#8B92A9' }}/>
                {timeData.machines.map((m, i) => (
                  <Line key={m} dataKey="global_score" data={timeData.series.filter(e => e.machine_id===m)}
                    name={m} type="monotone" stroke={LINE_COLORS[i % LINE_COLORS.length]}
                    strokeWidth={1.8} dot={{ r:2 }}/>
                ))}
              </LineChart>
            </ResponsiveContainer>
          </ChartCard>

          {heatmap.length > 0 && (
            <>
              <SectionHead action={
                <div style={{ display:'flex',alignItems:'center',gap:10,fontSize:10,color:'#525870' }}>
                  {[{ label:'≥ 7.5',color:'rgba(0,211,127,.65)' },{ label:'5.5–7.5',color:'rgba(255,176,32,.6)' },{ label:'< 5.5',color:'rgba(240,68,56,.58)' }].map(item => (
                    <span key={item.label} style={{ display:'flex',alignItems:'center',gap:4 }}>
                      <span style={{ width:8,height:8,borderRadius:2,background:item.color,display:'inline-block' }}/>
                      {item.label}
                    </span>
                  ))}
                </div>
              }>Heatmap — Conformité par machine</SectionHead>
              <div style={{ borderRadius:13,overflow:'hidden',border:'1px solid rgba(37,40,64,.7)',boxShadow:'0 4px 22px rgba(0,0,0,.2)' }}>
                <table style={{ width:'100%',borderCollapse:'collapse',fontSize:12 }}>
                  <thead>
                    <tr style={{ background:'rgba(24,27,42,.98)' }}>
                      <th style={{ padding:'11px 16px',textAlign:'left',fontSize:9,fontWeight:800,color:'#525870',textTransform:'uppercase',letterSpacing:'.9px',borderBottom:'1px solid rgba(37,40,64,.8)' }}>Machine</th>
                      {Object.values(CRITERIA).map(c => <th key={c} style={{ padding:'11px 10px',textAlign:'center',fontSize:8.5,fontWeight:800,color:'#525870',textTransform:'uppercase',letterSpacing:'.5px',borderBottom:'1px solid rgba(37,40,64,.8)' }}>{c}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {heatmap.map((row, i) => (
                      <tr key={i} style={{ background:i%2===0?'rgba(18,20,31,.92)':'rgba(13,15,24,.92)',transition:'background .12s' }}
                        onMouseEnter={e => (e.currentTarget.style.background='rgba(28,31,46,.95)')}
                        onMouseLeave={e => (e.currentTarget.style.background=i%2===0?'rgba(18,20,31,.92)':'rgba(13,15,24,.92)')}>
                        <td style={{ padding:'9px 16px',fontFamily:'JetBrains Mono,monospace',fontSize:11,color:'#C8CDD8',borderBottom:'1px solid rgba(37,40,64,.45)' }}>{row.machine}</td>
                        {Object.values(CRITERIA).map(c => {
                          const v = typeof row[c]==='number' ? row[c] as number : 0
                          const { bg, text } = heatColor(v)
                          return (
                            <td key={c} style={{ padding:'9px 10px',textAlign:'center',borderBottom:'1px solid rgba(37,40,64,.45)' }}>
                              <span style={{ display:'inline-block',padding:'3px 9px',borderRadius:6,background:bg,color:text,fontSize:11,fontWeight:800,fontFamily:'JetBrains Mono,monospace' }}>{v.toFixed(1)}</span>
                            </td>
                          )
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </>
      )}
    </div>
  )
}
