// 统一 HTTP 客户端：同源路径 + X-Trace-ID + CSRF + envelope 解析（docs/04 §1）
const SERVICE_BASES = {
  flowai: '/api/flowai',
  industrial: '/api/industrial'
}

let csrfToken = ''

export function setCsrfToken(token) {
  csrfToken = token || ''
}

export function getCsrfToken() {
  return csrfToken
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
  const requestHeaders = {
    Accept: 'application/json',
    'X-Trace-ID': traceId,
    ...(headers || {})
  }
  if (body !== undefined) requestHeaders['Content-Type'] = 'application/json'
  if (csrfToken) requestHeaders['X-CSRF-Token'] = csrfToken

  let response
  try {
    response = await fetch(`${base}${path}`, {
      method,
      credentials: 'include',
      headers: requestHeaders,
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
export const apiPatch = (service, path, options) => request('PATCH', service, path, options)
export const apiDelete = (service, path, options) => request('DELETE', service, path, options)

export async function uploadFile(service, path, file) {
  const form = new FormData()
  form.append('file', file)
  const response = await fetch(`${SERVICE_BASES[service]}${path}`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'X-Trace-ID': newTraceId(), ...(csrfToken ? { 'X-CSRF-Token': csrfToken } : {}) },
    body: form
  })
  let payload = {}
  try {
    payload = await response.json()
  } catch {
    payload = {}
  }
  return { ok: response.ok, status: response.status, data: payload.data || {}, code: payload.code }
}