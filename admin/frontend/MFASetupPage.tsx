import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { supabase } from "@/lib/supabase"

export function MFASetupPage() {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)
  const [qrCode, setQrCode] = useState<string | null>(null)
  const [totpCode, setTotpCode] = useState('')
  const [factorId, setFactorId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [step, setStep] = useState<'intro' | 'scan' | 'verify' | 'done'>('intro')

  const startEnrollment = async () => {
    setLoading(true)
    setError(null)
    try {
      const { data, error: err } = await supabase.auth.mfa.enroll({ factorType: 'totp' })
      if (err) throw err
      setQrCode(data.totp.qr_code)
      setFactorId(data.id)
      setStep('scan')
    } catch (e: any) {
      setError(e.message || 'Failed to start enrollment')
    } finally {
      setLoading(false)
    }
  }

  const verifyTotp = async () => {
    // Layer 2: Guard against submission without required data (button is also disabled, belt+suspenders)
    if (!factorId || !totpCode) return
    setLoading(true)
    setError(null)
    try {
      const { data: challengeData, error: challengeErr } = await supabase.auth.mfa.challenge({ factorId })
      if (challengeErr) throw challengeErr
      const { error: verifyErr } = await supabase.auth.mfa.verify({
        factorId,
        challengeId: challengeData.id,
        code: totpCode,
      })
      if (verifyErr) throw verifyErr
      setStep('done')
      // Redirect back to the app after a brief confirmation moment
      setTimeout(() => {
        if (typeof window !== 'undefined') {
          const params = new URLSearchParams(window.location.search);
          const returnUrl = params.get('returnUrl') || '/elein/campaigns';
          navigate(returnUrl);
        }
      }, 2000)
    } catch (e: any) {
      setError(e.message || 'Invalid code. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  // Layer 2: Only allow digits in the TOTP field to prevent obvious typos
  const handleTotpChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value.replace(/\D/g, '')
    setTotpCode(val)
  }

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <div className="max-w-md w-full bg-card border border-border rounded-2xl p-8 shadow-xl">
        <h1 className="text-2xl font-bold text-foreground mb-2">Set Up 2FA</h1>
        <p className="text-sm text-muted-foreground mb-6">
          Your workspace administrator requires two-factor authentication. Set up an authenticator app to continue.
        </p>

        {error && (
          <div className="mb-4 p-3 bg-destructive/10 border border-destructive/30 rounded-lg text-sm text-destructive">
            {error}
          </div>
        )}

        {step === 'intro' && (
          <button
            onClick={startEnrollment}
            disabled={loading}
            className="w-full py-3 bg-primary text-primary-foreground rounded-xl font-semibold hover:bg-primary/90 disabled:opacity-50"
          >
            {loading ? 'Starting...' : 'Set Up Authenticator App'}
          </button>
        )}

        {step === 'scan' && qrCode && (
          <div>
            <p className="text-sm text-muted-foreground mb-4">
              Scan this QR code with your authenticator app (Google Authenticator, Authy, etc.):
            </p>
            <img
              src={qrCode}
              alt="TOTP QR Code"
              className="w-48 h-48 mx-auto mb-6 rounded-lg border border-border"
            />
            <input
              type="text"
              inputMode="numeric"
              pattern="[0-9]*"
              value={totpCode}
              onChange={handleTotpChange}
              placeholder="Enter 6-digit code"
              maxLength={6}
              className="w-full px-3 py-2 bg-background border border-border rounded-lg text-center text-2xl font-mono tracking-widest mb-4 focus:border-primary outline-none"
            />
            {/* Layer 2: disabled until exactly 6 digits are entered — prevents premature submission */}
            <button
              onClick={verifyTotp}
              disabled={loading || totpCode.length !== 6}
              className="w-full py-3 bg-primary text-primary-foreground rounded-xl font-semibold hover:bg-primary/90 disabled:opacity-50"
            >
              {loading ? 'Verifying...' : 'Verify & Enable 2FA'}
            </button>
          </div>
        )}

        {step === 'done' && (
          <div className="text-center">
            <div className="w-16 h-16 bg-success/10 dark:bg-success/50/30 rounded-full flex items-center justify-center mx-auto mb-4">
              <span className="text-3xl">✓</span>
            </div>
            <p className="text-sm text-muted-foreground">2FA enabled! Redirecting you back...</p>
          </div>
        )}
      </div>
    </div>
  )
}
