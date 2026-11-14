import { test, expect } from '@playwright/test'
import type { APIRequestContext } from '@playwright/test'

/**
 * Composer harness picker.
 *
 * The harness chip beside the composer opens a menu that sets the agent new
 * chats start on (`agent.acp_backend`). That is the same setting as Settings ▸
 * Agents & plans ▸ Chat harness, so the spec checks the pick in three places
 * an operator can see: the menu's own check mark, the gateway's read-back
 * (`/api/routing/harnesses`), and the Settings radio group.
 *
 * The target is the first choice that is not the configured one and is not
 * marked not-installed. `auto` is always offered and always selectable, so the
 * credential-less CI gateway has a target. The original value is written back
 * afterwards through the same public endpoint the dashboard uses.
 */

interface ChatChoice { id: string; installed: boolean | null }
interface ChatView { configured: string; choices: ChatChoice[] }

async function chatView(request: APIRequestContext): Promise<ChatView> {
  const res = await request.get('/api/routing/harnesses')
  expect(res.ok()).toBeTruthy()
  return (await res.json()).chat as ChatView
}

test.describe('Composer harness picker', () => {
  let original = ''

  test.beforeEach(async ({ request }) => {
    original = (await chatView(request)).configured
  })

  test.afterEach(async ({ request }) => {
    await request.patch('/api/config/warding', { data: { path: 'agent.acp_backend', value: original } })
  })

  test('sets the agent new chats start on', async ({ page, request }) => {
    const before = await chatView(request)
    const target = before.choices.find(c => c.id !== before.configured && c.installed !== false)
    expect(target, 'auto is always a selectable choice').toBeTruthy()
    const targetId = target!.id

    await page.goto('/chat', { waitUntil: 'domcontentloaded' })
    await expect(page.getByPlaceholder(/message/i)).toBeVisible({ timeout: 10000 })

    const chip = page.getByTestId('composer-harness')
    await expect(chip).toBeVisible()
    await chip.click()

    const menu = page.getByTestId('composer-harness-menu')
    await expect(menu).toBeVisible()
    await expect(menu.getByTestId(`composer-harness-${before.configured}`)).toHaveAttribute('aria-checked', 'true')

    const pick = menu.getByTestId(`composer-harness-${targetId}`)
    await pick.click()
    // The menu stays open, so the moved check mark is visible after the pick.
    await expect(pick).toHaveAttribute('aria-checked', 'true')
    await expect(menu.getByTestId(`composer-harness-${before.configured}`)).toHaveAttribute('aria-checked', 'false')

    await expect.poll(async () => (await chatView(request)).configured).toBe(targetId)

    await page.keyboard.press('Escape')
    await expect(menu).toBeHidden()

    await page.goto('/settings/agents', { waitUntil: 'domcontentloaded' })
    await expect(page.getByTestId(`chat-harness-${targetId}`).getByRole('radio')).toHaveAttribute('aria-checked', 'true', { timeout: 10000 })
  })
})
