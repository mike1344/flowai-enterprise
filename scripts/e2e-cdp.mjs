// 通过 CDP 复用已启动的 Chrome 驱动 P0 端到端（规避 Playwright 子进程管道限制）
import { chromium } from '../frontend/node_modules/playwright-core/index.mjs'

const BASE = 'http://127.0.0.1:5173'
const results = []
function record(name, ok, detail = '') {
  results.push({ name, ok, detail })
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? ' :: ' + detail : ''}`)
}

const browser = await chromium.connectOverCDP('http://127.0.0.1:9222')
const context = await browser.newContext()
const page = await context.newPage()
const consoleErrors = []
const apiFailures = []
page.on('console', (msg) => {
  if (msg.type() === 'error') consoleErrors.push(msg.text())
})
page.on('response', (res) => {
  if (res.url().includes('/api/') && res.status() >= 400) {
    apiFailures.push(`${res.status()} ${res.request().method()} ${res.url()}`)
  }
})

try {
  await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' })
  await page.getByPlaceholder('用户名').fill('admin')
  await page.getByPlaceholder('口令').fill('Passw0rd!2026')
  await page.getByRole('button', { name: '登录' }).click()
  await page.waitForURL(/\/admin$/, { timeout: 15000 })
  await page.getByText('运行总览').first().waitFor({ timeout: 15000 })
  record('登录并进入管理端', true)

  await page.getByRole('menuitem', { name: 'AI 应用' }).click()
  await page.getByText('service-agent').first().waitFor({ timeout: 15000 })
  record('管理端应用列表可见', true)

  await page.getByRole('menuitem', { name: '知识库' }).click()
  await page.getByText('设备知识库').first().waitFor({ timeout: 15000 })
  await page.getByText('gateway.md').first().waitFor({ timeout: 15000 })
  record('知识库文档列表可见', true)

  // 通过应用列表“打开”按钮做客户端跳转（避免整页导航）
  await page.getByRole('menuitem', { name: 'AI 应用' }).click()
  const appRow = page.getByRole('row', { name: /service-agent/ })
  await appRow.waitFor({ timeout: 15000 })
  await appRow.getByRole('button', { name: '打开' }).click()
  await page.getByPlaceholder(/device_id/).waitFor({ timeout: 25000 })
  await page.getByPlaceholder(/device_id/).fill('device_id: 1 HC200 通信异常，请帮我创建工单')
  await page.getByRole('button', { name: '发送' }).click()
  await page.getByText('工单草稿（需人工确认后才会写入）').waitFor({ timeout: 25000 })
  record('未确认前出现工单草稿卡片', true)
  record('确认前无成功工单提示', (await page.getByText(/工单已创建：WO-/).count()) === 0)

  await page.getByRole('button', { name: '确认创建' }).click()
  await page.getByText(/工单已创建：WO-/).waitFor({ timeout: 30000 })
  const ticketText = await page.getByText(/工单已创建：WO-/).first().textContent()
  record('确认后创建真实工单', true, (ticketText || '').trim())

  await page.reload({ waitUntil: 'commit' }).catch(() => {})
  await page.getByPlaceholder(/device_id/).waitFor({ timeout: 25000 })
  await page.getByPlaceholder(/device_id/).fill('device_id: 2 SC100 采集异常，请帮我创建工单')
  await page.getByRole('button', { name: '发送' }).click()
  await page.getByText('工单草稿（需人工确认后才会写入）').waitFor({ timeout: 25000 })
  await page.getByRole('button', { name: '取消' }).click()
  await page.getByText(/已取消该操作/).waitFor({ timeout: 15000 })
  record('取消后不创建工单', true)
} catch (error) {
  record('执行异常', false, String(error).slice(0, 400))
} finally {
  record('浏览器控制台无错误', consoleErrors.length === 0, consoleErrors.slice(0, 3).join(' | '))
  if (apiFailures.length) console.log('API_FAILURES: ' + apiFailures.join(' | '))
  await page.close()
  await browser.close()
  const failed = results.filter((item) => !item.ok)
  console.log(`SUMMARY total=${results.length} passed=${results.length - failed.length} failed=${failed.length}`)
  process.exit(failed.length === 0 ? 0 : 1)
}