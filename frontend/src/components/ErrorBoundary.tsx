import { Component, type ReactNode, type ErrorInfo } from 'react'

interface Props   { children: ReactNode }
interface State   { hasError: boolean; error: Error | null }

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('[ErrorBoundary]', error, info.componentStack)
  }

  render(): ReactNode {
    if (!this.state.hasError) return this.props.children
    return (
      <div style={{
        margin: '40px auto', maxWidth: 520, padding: '28px 32px', borderRadius: 16,
        background: 'rgba(240,68,56,.06)', border: '1px solid rgba(240,68,56,.2)',
      }}>
        <div style={{ fontSize: 24, marginBottom: 12 }}>⚠</div>
        <div style={{ fontSize: 15, fontWeight: 600, color: '#E8ECF1', marginBottom: 8 }}>
          Une erreur est survenue
        </div>
        <div style={{ fontSize: 12, color: '#8B92A9', marginBottom: 20, lineHeight: 1.6 }}>
          {this.state.error?.message ?? 'Erreur inconnue dans ce composant.'}
        </div>
        <button
          onClick={() => this.setState({ hasError: false, error: null })}
          style={{
            padding: '8px 18px', borderRadius: 8, cursor: 'pointer',
            background: 'rgba(240,68,56,.12)', border: '1px solid rgba(240,68,56,.3)',
            color: '#F04438', fontSize: 12, fontWeight: 600,
          }}
        >
          ↺ Réessayer
        </button>
      </div>
    )
  }
}
