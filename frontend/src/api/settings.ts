const API_BASE = '/api/v1/settings'

export async function getSettings() {
  const resp = await fetch(`${API_BASE}/`)
  return resp.json()
}

export async function saveSettings(settings: Record<string, unknown>) {
  const resp = await fetch(`${API_BASE}/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ settings }),
  })
  return resp.json()
}
