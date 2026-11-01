import { expect, test } from '@playwright/test'

const USERNAME = 'admin'
const PASSWORD = 'Passw0rd!2026'
const SLUG = 'service-agent'
const DEVICE_ID = 1

async function login(page) {
  await page.goto('/login')
  await page.getByPlaceholder('用户名').fill(USERNAME)
  await page.getByPlaceholder('口令').fill(PASSWORD)
  await page.getByRole('button', { name: '登录' }).click()
  await expect(page).toHaveURL(/\/admin/)
}

test('管理端：登录后可查看应用列表（M05-01）', async ({ page }) => {
  await login(page)
  await page.getByRole('menuitem', { name: 'AI 应用' }).click()
  await expect(page.getByRole('heading', { name: 'AI 应用' })).toBeVisible()
  await expect(page.getByRole('cell', { name: SLUG })).toBeVisible()
})

test('管理端：知识库页展示已就绪文档（M05-01）', async ({ page }) => {
  await login(page)
  await page.getByRole('menuitem', { name: '知识库' }).click()
  await expect(page.getByRole('heading', { name: '知识库' })).toBeVisible()
  await page.getByRole('row', { name: /设备知识库/ }).click()
  await expect(page.getByRole('cell', { name: 'gateway.md' })).toBeVisible()
  await expect(page.getByText('已就绪 3 / 3')).toBeVisible()
})

test('应用端：对话 → 人工确认 → 创建工单闭环（M05-02）', async ({ page }) => {
  await login(page)
  await page.goto(`/apps/${SLUG}`)
  await expect(page.getByRole('heading', { name: SLUG })).toBeVisible()

  const input = page.getByPlaceholder(/device_id/)
  await input.fill(`device_id: ${DEVICE_ID} HC200 通信异常，请帮我创建工单`)
  await page.getByRole('button', { name: '发送' }).click()

  // 必须出现草稿确认卡片，且未确认前没有工单号
  await expect(page.getByText('工单草稿（需人工确认后才会写入）')).toBeVisible()
  await expect(page.getByText(/WO-/)).toHaveCount(0)

  await page.getByRole('button', { name: '确认创建' }).click()
  await expect(page.getByText(/工单已创建：WO-/)).toBeVisible({ timeout: 20000 })
})

test('应用端：取消确认不产生工单（M05-02 / M04-04）', async ({ page }) => {
  await login(page)
  await page.goto(`/apps/${SLUG}`)
  await page.getByPlaceholder(/device_id/).fill(`device_id: 2 SC100 采集异常，请帮我创建工单`)
  await page.getByRole('button', { name: '发送' }).click()
  await expect(page.getByText('工单草稿（需人工确认后才会写入）')).toBeVisible()

  await page.getByRole('button', { name: '取消' }).click()
  await expect(page.getByText(/已取消该操作/)).toBeVisible()
  await expect(page.getByText(/工单已创建：WO-/)).toHaveCount(0)
})