// 统一 HTTP 客户端：同源路径 + X-Trace-ID + envelope 解析（docs/04 §1）
const SERVICE_BASES = {
  flowai: '/api/flowai',
  industrial: '/api/industrial'
}

export function newTraceId() {
  const value =
    (globalThis.crypto && globalThis.crypto.randomUUID && globalThis.crypto.randomUUID()) ||
    `${Date.now()}-${Math.random().toString(16).slice(2)}`
  return String(value).replace(/-/g, '')
}

async function request(method, service, path, { body, headers } = {}) {
  const base = SERVICE_BASES[service]
  if (!base) throw new Error(`unknown service: ${service}`)

  const traceId = newTraceId()
  let response
  try {
    response = await fetch(`${base}${path}`, {
      method,
      credentials: 'include',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        'X-Trace-ID': traceId,
        ...(headers || {})
      },
      body: body === undefined ? undefined : JSON.stringify(body)
    })
  } catch (error) {
    return { ok: false, status: 0, code: 'NETWORK_ERROR', message: String(error), data: {}, traceId }
  }

  let payload = {}
  try {
    payload = await response.json()
  } catch {
    payload = {}
  }

  return {
    ok: response.ok && (payload.code === undefined || payload.code === 'SUCCESS'),
    status: response.status,
    code: payload.code || (response.ok ? 'SUCCESS' : 'UNKNOWN_ERROR'),
    message: payload.message || '',
    details: payload.details || {},
    data: payload.data || {},
    traceId: response.headers.get('X-Trace-ID') || payload.trace_id || traceId
  }
}

export const apiGet = (service, path, options) => request('GET', service, path, options)
export const apiPost = (service, path, options) => request('POST', service, path, options)