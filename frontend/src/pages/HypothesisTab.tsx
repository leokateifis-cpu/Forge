import { useState, useRef, useEffect } from 'react'
import { pipelineApi } from '../lib/api'
import { useAppStore } from '../store'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { Badge } from '../components/ui/Badge'
import { Spinner } from '../components/ui/Spinner'
import { useQueryClient } from '@tanstack/react-query'

interface Message {
  role: 'user' | 'assistant'
  content: string
}

export function HypothesisTab({ stage }: { stage: { status: string } }) {
  const { activeProjectId } = useAppStore()
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const qc = useQueryClient()

  const isLocked = stage?.status === 'complete' || stage?.status === 'skipped'

  useEffect(() => {
    if (messages.length === 0 && activeProjectId) {
      setMessages([
        {
          role: 'assistant',
          content:
            "Welcome to Forge. Let's define your trading hypothesis rigorously.\n\nWhat market inefficiency or behavioral pattern do you believe you've identified? Describe the edge you want to test — be as specific as you can about the instrument, timeframe, and the signal you expect to work.",
        },
      ])
    }
  }, [activeProjectId, messages.length])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function send() {
    if (!input.trim() || !activeProjectId) return
    const userMsg: Message = { role: 'user', content: input }
    setMessages((m) => [...m, userMsg])
    setInput('')
    setSending(true)
    try {
      const { data } = await pipelineApi.chat(activeProjectId, input)
      setMessages((m) => [
        ...m,
        { role: 'assistant', content: data.response },
      ])
      if (data.stage_advanced) {
        qc.invalidateQueries({ queryKey: ['pipeline', activeProjectId] })
      }
    } catch {
      setMessages((m) => [
        ...m,
        { role: 'assistant', content: '— error — please try again.' },
      ])
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-sm font-semibold text-white">Hypothesis Interview</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Forge will ask you structured questions to formalize your trading hypothesis.
          </p>
        </div>
        {isLocked && <Badge variant="success">Complete</Badge>}
      </div>

      <div className="flex-1 overflow-y-auto space-y-4 mb-4 min-h-0">
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[80%] rounded px-3 py-2 text-xs leading-relaxed whitespace-pre-wrap ${
                msg.role === 'user'
                  ? 'bg-indigo-600/20 border border-indigo-800 text-indigo-100'
                  : 'bg-[#13131f] border border-[#1e1e2e] text-slate-300'
              }`}
            >
              {msg.role === 'assistant' && (
                <span className="text-indigo-400 font-semibold block mb-1 text-[10px]">
                  FORGE
                </span>
              )}
              {msg.content}
            </div>
          </div>
        ))}
        {sending && (
          <div className="flex justify-start">
            <div className="bg-[#13131f] border border-[#1e1e2e] rounded px-3 py-2">
              <Spinner className="w-3 h-3" />
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {!isLocked && (
        <div className="flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && send()}
            placeholder="Describe your hypothesis..."
            className="flex-1 bg-[#13131f] border border-[#1e1e2e] rounded px-3 py-2 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-indigo-700"
          />
          <Button size="sm" onClick={send} loading={sending} disabled={!input.trim()}>
            Send
          </Button>
        </div>
      )}

      {isLocked && (
        <Card className="text-xs text-green-400 bg-green-500/5 border-green-900">
          Hypothesis locked. Proceed to Code Generation.
        </Card>
      )}
    </div>
  )
}
