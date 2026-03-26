import { useState, useRef, useEffect } from 'react'
import { Send, Bot, User, ChevronDown, ChevronUp, AlertTriangle } from 'lucide-react'

const API = import.meta.env.VITE_API_URL || ''

const SUGGESTIONS = [
  "Which products have the most billing documents?",
  "Show me sales orders not yet billed",
  "Trace the flow of a billing document",
  "Which customers have the highest order value?",
  "Find deliveries without billing documents",
  "What is the total billed amount?",
  "Show cancelled billing documents",
  "Which plants handle the most deliveries?",
]

function SqlBlock({ sql }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="sql-block">
      <div className="sql-toggle" onClick={() => setOpen(!open)}>
        {open ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
        <span>View SQL Query</span>
      </div>
      {open && <pre className="sql-code">{sql}</pre>}
    </div>
  )
}

function Message({ msg }) {
  const isUser = msg.role === 'user'
  const isOffTopic = msg.isRelevant === false
  const isError = msg.isError

  return (
    <div className={`chat-message ${isUser ? 'user' : 'assistant'}`}>
      <div className="msg-avatar">
        {isUser ? <User size={14} /> : <Bot size={14} />}
      </div>
      <div className="msg-content">
        <div className={`msg-bubble ${isOffTopic ? 'off-topic' : ''} ${isError ? 'error' : ''}`}>
          {isOffTopic && (
            <span style={{ marginRight: 6, color: 'var(--accent-orange)' }}>
              <AlertTriangle size={13} style={{ display: 'inline', verticalAlign: 'middle' }} />
            </span>
          )}
          {msg.content}
        </div>
        {msg.sql && <SqlBlock sql={msg.sql} />}
        {msg.rowCount != null && (
          <div className="results-count">
            {msg.rowCount} row{msg.rowCount !== 1 ? 's' : ''} returned
          </div>
        )}
      </div>
    </div>
  )
}

function ThinkingIndicator() {
  return (
    <div className="chat-message assistant">
      <div className="msg-avatar"><Bot size={14} /></div>
      <div className="msg-content">
        <div className="msg-bubble">
          <div className="thinking">
            <div className="thinking-dot" />
            <div className="thinking-dot" />
            <div className="thinking-dot" />
          </div>
        </div>
      </div>
    </div>
  )
}

export default function ChatPanel({ llmReady }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const messagesEndRef = useRef(null)
  const textareaRef = useRef(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  const sendMessage = async (text) => {
    const msg = text || input.trim()
    if (!msg || loading) return

    setInput('')
    setMessages(prev => [...prev, { role: 'user', content: msg, id: Date.now() }])
    setLoading(true)

    try {
      const res = await fetch(`${API}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: msg }),
      })

      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || `HTTP ${res.status}`)
      }

      const data = await res.json()
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: data.answer,
        sql: data.sql,
        rowCount: data.row_count,
        isRelevant: data.is_relevant,
        id: Date.now(),
      }])
    } catch (e) {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `Error: ${e.message}. Please try again.`,
        isError: true,
        id: Date.now(),
      }])
    } finally {
      setLoading(false)
    }
  }

  const handleKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  return (
    <div className="chat-panel">
      <div className="chat-header">
        <div className="chat-header-icon">🤖</div>
        <div className="chat-header-info">
          <h3>O2C Query Assistant</h3>
          <p>{llmReady ? '● Connected to Gemini' : '○ LLM not configured'}</p>
        </div>
      </div>

      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="chat-welcome">
            <div className="welcome-icon">📊</div>
            <div className="welcome-title">Ask about your O2C data</div>
            <div className="welcome-sub">
              Query sales orders, deliveries, billing documents, payments, and more using natural language.
            </div>
          </div>
        )}

        {messages.map(m => <Message key={m.id} msg={m} />)}
        {loading && <ThinkingIndicator />}
        <div ref={messagesEndRef} />
      </div>

      {/* Suggestions */}
      {messages.length === 0 && (
        <div className="chat-suggestions">
          <div className="suggestions-label">Try asking</div>
          <div className="suggestion-chips">
            {SUGGESTIONS.slice(0, 6).map((s, i) => (
              <button key={i} className="suggestion-chip" onClick={() => sendMessage(s)}>
                {s}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="chat-input-area">
        <div className="chat-input-row">
          <textarea
            ref={textareaRef}
            className="chat-input"
            placeholder={llmReady ? "Ask a question about the O2C data…" : "Configure GEMINI_API_KEY to enable chat"}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKey}
            disabled={!llmReady || loading}
            rows={1}
          />
          <button
            className="chat-send-btn"
            onClick={() => sendMessage()}
            disabled={!llmReady || loading || !input.trim()}
          >
            <Send size={15} />
          </button>
        </div>
      </div>
    </div>
  )
}
