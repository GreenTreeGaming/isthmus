import { Component, type ReactNode } from 'react'

interface State {
  error: Error | null
}

/** Keeps one broken view from blanking the whole app. */
export class ErrorBoundary extends Component<{ children: ReactNode; label: string }, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error) {
    console.error(`[${this.props.label}]`, error)
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className="crash">
        <div className="crash-box">
          <h3>The {this.props.label} hit a problem</h3>
          <p className="muted">{this.state.error.message}</p>
          <button className="run" onClick={() => this.setState({ error: null })}>Try again</button>
        </div>
      </div>
    )
  }
}
