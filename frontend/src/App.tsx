
import { useEffect, useState } from 'react'
import './App.css'
import ReactMarkdown from 'react-markdown'

type Page = 'Overview' | 'Assistant' | 'Tool Catalog' | 'Execution History'

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

const navigation: { label: Page; icon: string }[] = [
  { label: 'Overview', icon: '◫' },
  { label: 'Assistant', icon: '✳' },
  { label: 'Tool Catalog', icon: '⌘' },
  { label: 'Execution History', icon: '↗' },
]

type ApiTool = {
  name: string
  description: string
}

type DisplayTool = ApiTool & {
  id: string
  category: string
  color: string
}

type ExecutionRecord = {
  id: number
  tool_name: string
  status: string
  duration_ms: number
  error_message: string | null
  created_at: string
  input: Record<string, unknown>
  output: unknown
}

const toolPresentation: Record<
  string,
  { category: string; color: string }
> = {
  check_order_status: { category: 'Orders', color: 'blue' },
  get_business_hours: { category: 'Information', color: 'purple' },
  create_support_ticket: { category: 'Support', color: 'green' },
  book_demo: { category: 'Scheduling', color: 'orange' },
}

type AssistantResponse = {
  status: string
  tool_name: string | null
  tool_result: unknown
  answer: string
  conversation_id?: number
}

type ChatMessage = {
  id?: number
  role: 'user' | 'assistant'
  text: string
  details?: AssistantResponse
}

type ConversationSummary = {
  id: number
  title: string
  created_at: string
  updated_at: string
}

type StoredMessage = {
  id: number
  role: 'user' | 'assistant'
  content: string
  details: AssistantResponse | null
  created_at: string
}

type StoredConversation = ConversationSummary & {
  messages: StoredMessage[]
}


function AssistantChat() {
  const [prompt, setPrompt] = useState('')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [conversations, setConversations] = useState<ConversationSummary[]>([])
  const [activeId, setActiveId] = useState<number | null>(null)
  const [loading, setLoading] = useState(false)
  const [historyLoading, setHistoryLoading] = useState(true)
  const [error, setError] = useState('')

  async function openConversation(id: number) {
    setError('')
    setHistoryLoading(true)
    setActiveId(id)

    try {
      const response = await fetch(
        `${API_BASE_URL}/conversations/${id}`,
      )

      const data = await response.json()

      if (!response.ok) {
        throw new Error(
          typeof data.detail === 'string'
            ? data.detail
            : 'Could not open this conversation.',
        )
      }

      const conversation = data as StoredConversation

      setMessages(
        conversation.messages.map((message) => ({
          id: message.id,
          role: message.role,
          text: message.content,
          details: message.details ?? undefined,
        })),
      )
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Could not load the conversation.',
      )
    } finally {
      setHistoryLoading(false)
    }
  }

  async function refreshConversationList() {
    const response = await fetch(`${API_BASE_URL}/conversations`)

    if (!response.ok) {
      throw new Error('Could not load saved conversations.')
    }

    const data: { conversations: ConversationSummary[] } =
      await response.json()

    setConversations(data.conversations)
    return data.conversations
  }

  useEffect(() => {
    let cancelled = false

    async function loadSavedChats() {
      try {
        const response = await fetch(
          `${API_BASE_URL}/conversations`,
        )

        if (!response.ok) {
          throw new Error('Could not load saved conversations.')
        }

        const data: { conversations: ConversationSummary[] } =
          await response.json()

        if (cancelled) return

        setConversations(data.conversations)

        // Restore the most recently updated chat without calling Gemini.
        if (data.conversations.length > 0) {
          await openConversation(data.conversations[0].id)
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : 'Could not load saved conversations.',
          )
        }
      } finally {
        if (!cancelled) {
          setHistoryLoading(false)
        }
      }
    }

    void loadSavedChats()

    return () => {
      cancelled = true
    }
  }, [])

  async function startNewChat() {
    if (loading) return

    setError('')
    setHistoryLoading(true)

    try {
      const response = await fetch(
        `${API_BASE_URL}/conversations`,
        { method: 'POST' },
      )

      const data: ConversationSummary & { id: number } =
        await response.json()

      if (!response.ok) {
        throw new Error('Could not create a new conversation.')
      }

      setConversations((previous) => [data, ...previous])
      setActiveId(data.id)
      setMessages([])
      setPrompt('')
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Could not create a new conversation.',
      )
    } finally {
      setHistoryLoading(false)
    }
  }

  async function sendMessage() {
    const text = prompt.trim()

    if (!text || loading) return

    setPrompt('')
    setError('')
    setLoading(true)

    // Display the user's message immediately.
    setMessages((previous) => [...previous, { role: 'user', text }])

    let conversationId = activeId

    try {
      // The first message can create a conversation automatically.
      if (conversationId === null) {
        const createResponse = await fetch(
          `${API_BASE_URL}/conversations`,
          { method: 'POST' },
        )

        const created: ConversationSummary = await createResponse.json()

        if (!createResponse.ok) {
          throw new Error('Could not create a conversation.')
        }

        conversationId = created.id
        setActiveId(created.id)
        setConversations((previous) => [created, ...previous])
      }

      const response = await fetch(`${API_BASE_URL}/assistant`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt: text,
          conversation_id: conversationId,
        }),
      })

      const data = await response.json()

      if (!response.ok) {
        throw new Error(
          typeof data.detail === 'string'
            ? data.detail
            : `Request failed with HTTP ${response.status}`,
        )
      }

      const result = data as AssistantResponse

      setMessages((previous) => [
        ...previous,
        {
          role: 'assistant',
          text: result.answer,
          details: result,
        },
      ])

      // Refresh titles and ordering after the conversation changes.
      await refreshConversationList()
    } catch (err) {
      if (err instanceof TypeError) {
        setError(
          'Could not reach the ToolPilot backend. Check the API URL and try again.',
        )
      } else {
        setError(
          err instanceof Error
            ? err.message
            : 'An unexpected error occurred.',
        )
      }

      // The backend saves the user's prompt before processing it.
      // Reload to reflect the database's actual state after a failure.
      if (conversationId !== null) {
        try {
          await openConversation(conversationId)
          await refreshConversationList()
        } catch {
          // Keep the original request error visible.
        }
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="conversation-layout">
      <aside className="panel conversation-sidebar">
        <div className="conversation-sidebar-heading">
          <div>
            <h2>Conversations</h2>
            <p>Your saved chats</p>
          </div>
          <button
            type="button"
            className="primary-button"
            onClick={() => void startNewChat()}
            disabled={loading || historyLoading}
          >
            + New
          </button>
        </div>

        {historyLoading && conversations.length === 0 && (
          <p className="history-message">Loading conversations…</p>
        )}

        {!historyLoading && conversations.length === 0 && (
          <p className="history-message">
            No saved chats yet. Send a message to get started.
          </p>
        )}

        <div className="conversation-list">
          {conversations.map((conversation) => (
            <button
              type="button"
              key={conversation.id}
              className={`conversation-item ${
                activeId === conversation.id ? 'active' : ''
              }`}
              onClick={() => void openConversation(conversation.id)}
              disabled={loading || historyLoading}
            >
              <strong>{conversation.title || 'New chat'}</strong>
              <small>
                {new Date(
                  `${conversation.updated_at.replace(' ', 'T')}Z`,
                ).toLocaleString(undefined, {
                  month: 'short',
                  day: 'numeric',
                  hour: '2-digit',
                  minute: '2-digit',
                })}
              </small>
            </button>
          ))}
        </div>
      </aside>

      <div className="panel assistant-chat">
        <div className="chat-messages">
          {historyLoading && (
            <p className="history-message">Opening conversation…</p>
          )}

          {!historyLoading && messages.length === 0 && (
            <div className="chat-empty">
              <div className="assistant-orb">✳</div>
              <h2>Your workflow assistant</h2>
              <p>
                Ask a question or request an action supported by your
                registered tools.
              </p>
              <div className="suggestion-list">
                <button
                  onClick={() =>
                    setPrompt('What are the business hours on Monday?')
                  }
                >
                  Ask about business hours <span>→</span>
                </button>
                <button
                  onClick={() =>
                    setPrompt('Check the status of order ORD-1001')
                  }
                >
                  Check an order status <span>→</span>
                </button>
              </div>
            </div>
          )}

          {messages.map((message, index) => (
            <div
              className={`chat-message ${message.role}`}
              key={message.id ?? `${message.role}-${index}`}
            >
              <div className="chat-role">
                {message.role === 'user' ? 'You' : 'ToolPilot'}
              </div>
              <div className="chat-bubble">
                <ReactMarkdown>{message.text}</ReactMarkdown>
              </div>

              {message.details && (
                <div className="chat-result">
                  <div className="result-heading">
                    <strong>Execution details</strong>
                    <span
                      className={`status-badge ${
                        message.details.status === 'tool_failed'
                          ? 'failed'
                          : message.details.status === 'tool_executed'
                            ? 'success'
                            : 'neutral'
                      }`}
                    >
                      <span />
                      {message.details.status}
                    </span>
                  </div>

                  {message.details.tool_name && (
                    <p>
                      <strong>Tool:</strong>{' '}
                      <code>{message.details.tool_name}</code>
                    </p>
                  )}

                  {message.details.tool_result != null && (
                    <details>
                      <summary>View raw tool result</summary>
                      <pre>
                        {JSON.stringify(
                          message.details.tool_result,
                          null,
                          2,
                        )}
                      </pre>
                    </details>
                  )}
                </div>
              )}
            </div>
          ))}

          {loading && (
            <div className="chat-message assistant">
              <div className="chat-role">ToolPilot</div>
              <div className="chat-bubble">
                Thinking and processing your request…
              </div>
            </div>
          )}
        </div>

        {error && <div className="chat-error">{error}</div>}

        <form
          className="chat-composer"
          onSubmit={(event) => {
            event.preventDefault()
            void sendMessage()
          }}
        >
          <input
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            placeholder="Ask ToolPilot to do something…"
            maxLength={4000}
            disabled={loading || historyLoading}
          />
          <button
            type="submit"
            className="primary-button"
            disabled={loading || historyLoading || !prompt.trim()}
          >
            {loading ? 'Working…' : 'Send ↑'}
          </button>
        </form>

        <p className="chat-disclaimer">
          Requests are processed by your local backend. Tool actions may have
          side effects.
        </p>
      </div>
    </div>
  )
}

function App() {
  const [page, setPage] = useState<Page>('Overview')
  const [tools, setTools] = useState<DisplayTool[]>([])
  const [toolsLoading, setToolsLoading] = useState(true)
  const [toolsError, setToolsError] = useState('')
  const [executions, setExecutions] = useState<ExecutionRecord[]>([])
  const [executionsLoading, setExecutionsLoading] = useState(false)
  const [executionsError, setExecutionsError] = useState('')

  useEffect(() => {
    const controller = new AbortController()

    async function loadTools() {
      try {
        setToolsLoading(true)
        setToolsError('')

        const response = await fetch(`${API_BASE_URL}/tools`, {
          signal: controller.signal,
        })

        if (!response.ok) {
          throw new Error(`Backend returned HTTP ${response.status}`)
        }

        const data: { tools: ApiTool[] } = await response.json()

        setTools(
          data.tools.map((tool) => ({
            ...tool,
            id: tool.name,
            ...(toolPresentation[tool.name] ?? {
              category: 'General',
              color: 'blue',
            }),
          })),
        )
      } catch (error) {
        if (error instanceof Error && error.name !== 'AbortError') {
          setToolsError(error.message)
        }
      } finally {
        if (!controller.signal.aborted) {
          setToolsLoading(false)
        }
      }
    }

    void loadTools()

    return () => controller.abort()
  }, [])

  useEffect(() => {
  const controller = new AbortController()

  async function loadExecutions() {
    try {
      setExecutionsLoading(true)
      setExecutionsError('')

      const response = await fetch(
        `${API_BASE_URL}/executions?limit=100`,
        { signal: controller.signal },
      )

      if (!response.ok) {
        throw new Error(`Backend returned HTTP ${response.status}`)
      }

      const data: { executions: ExecutionRecord[] } =
        await response.json()

      setExecutions(data.executions)
    } catch (error) {
      if (error instanceof Error && error.name !== 'AbortError') {
        setExecutionsError(error.message)
      }
    } finally {
      if (!controller.signal.aborted) {
        setExecutionsLoading(false)
      }
    }
  }

  void loadExecutions()

  return () => controller.abort()
}, [page])

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="#" onClick={() => setPage('Overview')}>
          <span className="brand-mark">T</span>
          <span className="brand-copy">
            <strong>toolpilot</strong>
            <small>WORKFLOW ENGINE</small>
          </span>
        </a>

        <div className="workspace-label">WORKSPACE</div>
        <nav className="navigation">
          {navigation.map((item) => (
            <button
              key={item.label}
              className={`nav-item ${page === item.label ? 'active' : ''}`}
              onClick={() => setPage(item.label)}
            >
              <span className="nav-icon">{item.icon}</span>
              {item.label}
              {item.label === 'Execution History' && (
  <span className="nav-count">{executions.length}</span>
)}
            </button>
          ))}
        </nav>

        <div className="sidebar-bottom">
          <div className="engine-card">
            <span className="status-dot" />
            <div>
              <strong>Engine status</strong>
              <small>Engine connected</small>
            </div>
          </div>
          <div className="profile">
            <div className="avatar">SP</div>
            <div className="profile-copy">
              <strong>Workspace owner</strong>
              <small>Local development</small>
            </div>
            <span className="profile-menu">···</span>
          </div>
        </div>
      </aside>

      <main className="main-panel">
        <header className="topbar">
          <div className="breadcrumbs">
            <span>Workspace</span><span className="crumb-slash">/</span>
            <strong>{page}</strong>
          </div>
          <div className="topbar-right">
            <span className="preview-pill"><span /> Live Backend</span>
            <button className="help-button" title="Help">?</button>
          </div>
        </header>

        <div className="page-content">
          {page === 'Overview' && (
            <>
              <section className="welcome-row">
                <div>
                  <div className="eyebrow">YOUR WORKSPACE AT A GLANCE</div>
                  <h1>Good to see you.</h1>
                  <p className="subtitle">
                    Your AI tools, execution activity, and workflow health — all in one place.
                  </p>
                </div>
                <button className="primary-button" onClick={() => setPage('Assistant')}>
                  <span>＋</span> Open assistant
                </button>
              </section>

              <section className="metrics-grid">
                <Metric
                  label="Recent executions"
                  value={executionsLoading && executions.length === 0 ? '…' : String(executions.length)}
                  change="Latest 100 records"
                  icon="↗"
                  color="blue"
                />
                <Metric
                  label="Successful runs"
                  value={String(executions.filter((item) => item.status === 'success').length)}
                  change="In loaded history"
                  icon="✓"
                  color="green"
                />
                <Metric
                  label="Failed runs"
                  value={String(executions.filter((item) => item.status === 'failed').length)}
                  change="In loaded history"
                  icon="!"
                  color="red"
                />
                <Metric
                  label="Registered tools"
                  value={toolsLoading ? '…' : String(tools.length).padStart(2, '0')}
                  change="Live backend data"
                  icon="⌘"
                  color="purple"
                />
              </section>

              <section className="content-grid">
                <div className="panel activity-panel">
                  <div className="panel-heading">
                    <div>
                      <h2>Recent executions</h2>
                      <p>A quick look at recent tool activity.</p>
                    </div>
                    <button className="text-button" onClick={() => setPage('Execution History')}>
                      View history <span>→</span>
                    </button>
                  </div>
                  <ActivityTable
                    compact
                    executions={executions.slice(0, 4)}
                    loading={executionsLoading}
                    error={executionsError}
                  />
                </div>

                <div className="panel tools-panel">
                  <div className="panel-heading">
                    <div>
                      <h2>Registered tools</h2>
                      <p>Actions available to the engine.</p>
                    </div>
                    <button className="icon-button" onClick={() => setPage('Tool Catalog')}>↗</button>
                  </div>
                  <div className="tool-list">
                    {tools.map((tool) => (
                      <div className="tool-row" key={tool.id}>
                        <div className={`tool-icon ${tool.color}`}>⌘</div>
                        <div className="tool-copy">
                          <strong>{tool.name}</strong>
                          <small>{tool.id}</small>
                        </div>
                        <span className="available-dot" title="Listed in demo catalog" />
                      </div>
                    ))}
                  </div>
                  <button className="full-width-button" onClick={() => setPage('Tool Catalog')}>
                    Explore tool catalog <span>→</span>
                  </button>
                </div>
              </section>

              <section className="info-banner">
                <div className="info-symbol">✳</div>
                <div>
                  <strong>Designed for controlled execution.</strong>
                  <p>The engine validates tool arguments and routes requests through registered handlers. ToolPilot routes requests through registered tools, validates arguments, and records execution results from the live backend.</p>
                </div>
              </section>
            </>
          )}

          {page === 'Assistant' && (
            <section className="subpage">
              <div className="eyebrow">NATURAL LANGUAGE WORKFLOWS</div>
              <h1>Assistant</h1>
              <p className="subtitle">
                Describe what you need. ToolPilot will use your existing backend.
              </p>
              <AssistantChat />
            </section>
          )}

          {page === 'Tool Catalog' && (
            <section className="subpage">
              <div className="eyebrow">REGISTERED CAPABILITIES</div>
              <h1>Tool catalog</h1>
              <p className="subtitle">The actions your engine knows how to execute.</p>
              <div className="catalog-grid">
                {toolsLoading && <p>Loading tools from the backend…</p>}

                {toolsError && (
                  <div className="panel catalog-card">
                    <h2>Couldn't load tools</h2>
                    <p>{toolsError}</p>
                    <button
                      className="primary-button"
                      onClick={() => window.location.reload()}
                    >
                      Retry
                    </button>
                  </div>
                )}

                {!toolsLoading && !toolsError && tools.length === 0 && (
                  <p>No tools are currently registered.</p>
                )}

                {!toolsLoading && !toolsError && (
                  <div className="catalog-grid">
                    {tools.map((tool) => (
                      <article className="panel catalog-card" key={tool.id}>
                        <div className={`tool-icon large ${tool.color}`}>⌘</div>
                        <span className="category-label">{tool.category}</span>
                        <h2>{toolPresentation[tool.id] ? tool.name.replaceAll('_', ' ') : tool.name}</h2>
                        <code>{tool.id}</code>
                        <p>{tool.description}</p>
                        <p>Registered by the live backend</p>
                      </article>
                    ))}
                  </div>
                )}
              </div>
            </section>
          )}

          {page === 'Execution History' && (
            <section className="subpage">
              <div className="eyebrow">OBSERVABILITY</div>
              <h1>Execution history</h1>
              <p className="subtitle">Inspect recent tool activity and outcomes.</p>
              <div className="panel activity-panel">
                <div className="panel-heading">
                  <div>
                    <h2>All recent activity</h2>
                    <p>Recorded tool executions from your local database.</p>
                  </div>
                  <button
                    className="text-button"
                    onClick={() => setPage('Overview')}
                  >
                    Back to overview →
                  </button>
                </div>
                <ActivityTable
                  executions={executions}
                  loading={executionsLoading}
                  error={executionsError}
                />
              </div>
            </section>
          )}

          <footer className="page-footer">
            <span>ToolPilot <span className="footer-dot">·</span> AI workflow console</span>
            <span>Local preview <span className="footer-dot">·</span> Connected to local backend</span>
          </footer>
        </div>
      </main>
    </div>
  )
}

function Metric({
  label, value, change, icon, color,
}: {
  label: string
  value: string
  change: string
  icon: string
  color: string
}) {
  return (
    <article className="panel metric-card">
      <div className={`metric-icon ${color}`}>{icon}</div>
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value}</div>
      <div className="metric-footnote">{change}</div>
    </article>
  )
}

function ActivityTable({
  compact = false,
  executions,
  loading = false,
  error = '',
}: {
  compact?: boolean
  executions: ExecutionRecord[]
  loading?: boolean
  error?: string
}) {
  function displayName(name: string) {
    return name
      .split('_')
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join(' ')
  }

  function formatTime(value: string) {
    const date = new Date(`${value.replace(' ', 'T')}Z`)

    if (Number.isNaN(date.getTime())) return value

    return date.toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  }

  if (loading && executions.length === 0) {
    return <p className="history-message">Loading execution history…</p>
  }

  if (error && executions.length === 0) {
    return <p className="history-message history-error">{error}</p>
  }

  if (executions.length === 0) {
    return <p className="history-message">No executions recorded yet.</p>
  }

  return (
    <div className="table-wrap">
      {error && (
        <p className="history-message history-error">
          Refresh failed: {error}
        </p>
      )}

      <table>
        <thead>
          <tr>
            <th>TOOL</th>
            <th>STATUS</th>
            {!compact && <th>DURATION</th>}
            <th>WHEN</th>
          </tr>
        </thead>

        <tbody>
          {executions.map((execution) => {
            const failed = execution.status.toLowerCase() === 'failed'

            return (
              <tr key={execution.id}>
                <td>
                  <div className="table-tool">
                    <span className="table-tool-mark">⌘</span>
                    <div>
                      <strong>{displayName(execution.tool_name)}</strong>
                      <small>Execution #{execution.id}</small>
                    </div>
                  </div>
                </td>

                <td>
                  <span
                    className={`status-badge ${failed ? 'failed' : 'success'}`}
                  >
                    <span />
                    {execution.status}
                  </span>
                </td>

                {!compact && (
                  <td className="duration">
                    {execution.duration_ms.toFixed(2)} ms
                  </td>
                )}

                <td className="time-cell">
                  {formatTime(execution.created_at)}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export default App
