import { useState, useEffect } from 'react'
import './App.css'
import AgentPage from './AgentPage'
import KnowledgePage from './KnowledgePage'
import ScrapePage from './ScrapePage'

type Tab = 'agent' | 'knowledge' | 'scrape'

function getStoredTheme(): 'light' | 'dark' | null {
  return (localStorage.getItem('theme') as 'light' | 'dark') ?? null
}

export default function App() {
  const [tab, setTab] = useState<Tab>('agent')
  const [theme, setTheme] = useState<'light' | 'dark' | null>(getStoredTheme)

  useEffect(() => {
    const root = document.documentElement
    if (theme === 'dark') {
      root.setAttribute('data-theme', 'dark')
    } else if (theme === 'light') {
      root.setAttribute('data-theme', 'light')
    } else {
      root.removeAttribute('data-theme')
    }
    if (theme) localStorage.setItem('theme', theme)
    else localStorage.removeItem('theme')
  }, [theme])

  const toggleTheme = () => {
    setTheme(t => {
      if (t === null) return 'dark'
      if (t === 'dark') return 'light'
      return null
    })
  }

  const themeIcon = theme === 'dark' ? '☀' : theme === 'light' ? '◑' : '☾'

  return (
    <div className="app">
      <header className="header">
        <div className="header-brand">
          <div className="header-logo">M</div>
          <span className="header-title">Mergine</span>
        </div>
        <div className="header-sep" />
        <span className="header-badge">Scraper Agent</span>
        <div className="header-actions">
          <button
            className={`header-btn${tab === 'agent' ? ' active' : ''}`}
            onClick={() => setTab('agent')}
          >
            Agent
          </button>
          <button
            className={`header-btn${tab === 'knowledge' ? ' active' : ''}`}
            onClick={() => setTab('knowledge')}
          >
            Knowledge
          </button>
          <button
            className={`header-btn${tab === 'scrape' ? ' active' : ''}`}
            onClick={() => setTab('scrape')}
          >
            Scrape
          </button>
          <button className="theme-btn" onClick={toggleTheme} title="테마 전환">
            {themeIcon}
          </button>
        </div>
      </header>

      {tab === 'agent' && <AgentPage />}
      {tab === 'knowledge' && <KnowledgePage />}
      {tab === 'scrape' && <ScrapePage />}
    </div>
  )
}
