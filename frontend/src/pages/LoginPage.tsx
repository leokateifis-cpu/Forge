import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { authApi } from '../lib/api'
import { useAppStore } from '../store'
import { Button } from '../components/ui/Button'

export function LoginPage() {
  const navigate = useNavigate()
  const { setToken, setUser } = useAppStore()
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function submit() {
    setError('')
    setLoading(true)
    try {
      if (mode === 'register') {
        await authApi.register(email, password)
      }
      const { data } = await authApi.login(email, password)
      setToken(data.access_token)
      const me = await authApi.me()
      setUser(me.data)
      navigate('/app')
    } catch (e: any) {
      setError(e.response?.data?.detail ?? 'Authentication failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0a0a0f]">
      <div className="w-full max-w-sm px-6">
        {/* Logo */}
        <div className="mb-8 text-center">
          <span className="text-2xl font-bold font-mono text-white tracking-tight">
            ⬡ FORGE
          </span>
          <p className="text-xs text-slate-500 mt-1">Quantitative Research Platform</p>
        </div>

        <div className="bg-[#13131f] border border-[#1e1e2e] rounded-lg p-6 space-y-4">
          {/* Tab switch */}
          <div className="flex border border-[#1e1e2e] rounded overflow-hidden">
            {(['login', 'register'] as const).map((m) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={`flex-1 py-1.5 text-xs font-mono transition-colors ${
                  mode === m ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {m === 'login' ? 'Log in' : 'Create account'}
              </button>
            ))}
          </div>

          <input
            type="email"
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full bg-[#0a0a0f] border border-[#1e1e2e] rounded px-3 py-2 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-indigo-700"
          />
          <input
            type="password"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && submit()}
            className="w-full bg-[#0a0a0f] border border-[#1e1e2e] rounded px-3 py-2 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-indigo-700"
          />

          {error && (
            <div className="text-xs text-red-400 bg-red-500/10 rounded px-3 py-2">{error}</div>
          )}

          <Button className="w-full justify-center" loading={loading} onClick={submit}>
            {mode === 'login' ? 'Log in' : 'Create account'}
          </Button>
        </div>
      </div>
    </div>
  )
}
