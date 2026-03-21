/**
 * E2E tests for pages added in N-61 through N-63:
 *   - /import-wizard  (WorkflowImportWizard — N-62)
 *   - /api-keys       (ApiKeyManagerPage — N-63)
 *   - /node-config    (NodeConfigPage — N-61 SchemaForm demo)
 */
import { expect, test } from '@playwright/test';

// ---------------------------------------------------------------------------
// Helper: inject auth and optional API route mocks, then navigate
// ---------------------------------------------------------------------------
async function gotoWithAuth(
  page: Parameters<typeof test['fn']>[0]['page'],
  path: string,
  routes: Record<string, object> = {},
) {
  await page.addInitScript(() => {
    window.localStorage.setItem('access_token', 'e2e-test-token');
    window.localStorage.setItem(
      'auth_user',
      JSON.stringify({ id: 'e2e-user', email: 'e2e@test.com', is_active: true, created_at: 0 }),
    );
    // Mark onboarding complete to prevent dashboard → /onboarding redirect
    window.localStorage.setItem(
      'synapps_onboarding',
      JSON.stringify({ completed: [true, true, true] }),
    );
  });
  for (const [pattern, body] of Object.entries(routes)) {
    await page.route(pattern, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(body),
      });
    });
  }
  await page.goto(path);
}

const TEST_KEYS = [
  { id: 'key-1', name: 'Production Key', key_prefix: 'sk-***abc', is_active: true, created_at: 1704067200, last_used_at: null },
  { id: 'key-2', name: 'Dev Key', key_prefix: 'sk-***xyz', is_active: true, created_at: 1704153600, last_used_at: null },
];
const PAGED_KEYS = { items: TEST_KEYS, total: 2, page: 1, page_size: 20, total_pages: 1 };

// ===========================================================================
// Import Wizard (N-62)
// ===========================================================================

test('Import Wizard: renders step 1 with format selection', async ({ page }) => {
  await gotoWithAuth(page, '/import-wizard');
  await expect(page.getByTestId('step-1')).toBeVisible({ timeout: 15000 });
  await expect(page.getByRole('heading', { name: 'Select Workflow Format' })).toBeVisible();
  await expect(page.getByRole('radio', { name: 'n8n' })).toBeVisible();
  await expect(page.getByRole('radio', { name: 'Zapier' })).toBeVisible();
  await expect(page.getByRole('radio', { name: /synapps/i })).toBeVisible();
});

test('Import Wizard: advances to step 2 after clicking Next', async ({ page }) => {
  await gotoWithAuth(page, '/import-wizard');
  await page.getByTestId('step-1').waitFor({ timeout: 15000 });
  await page.getByRole('button', { name: 'Next' }).click();
  await expect(page.getByTestId('step-2')).toBeVisible();
  await expect(page.getByTestId('json-textarea')).toBeVisible();
});

test('Import Wizard: completes import and shows Open in Editor', async ({ page }) => {
  const importResponse = { id: 'flow-imported', flow_id: 'flow-imported', name: 'Imported Flow', nodes_imported: 2, edges_imported: 1 };
  await gotoWithAuth(page, '/import-wizard', { '**/workflows/import': importResponse });

  await page.getByTestId('step-1').waitFor({ timeout: 15000 });
  await page.getByRole('button', { name: 'Next' }).click();  // → step 2

  const sampleJson = JSON.stringify({
    nodes: [{ id: 'n1', type: 'start', position: { x: 0, y: 0 }, data: {} }, { id: 'n2', type: 'end', position: { x: 0, y: 100 }, data: {} }],
    edges: [{ id: 'e1', source: 'n1', target: 'n2' }],
  });
  await page.getByTestId('json-textarea').fill(sampleJson);
  await page.getByTestId('step2-next').click();  // → step 3

  await expect(page.getByTestId('import-button')).toBeVisible();
  await page.getByTestId('import-button').click();

  await expect(page.getByTestId('import-success')).toBeVisible({ timeout: 5000 });
  await expect(page.getByTestId('open-editor-link')).toBeVisible();
});

test('Import Wizard: accessible via Import nav link', async ({ page }) => {
  await gotoWithAuth(page, '/dashboard');
  await page.getByRole('link', { name: /Import/ }).click();
  await expect(page).toHaveURL(/\/import-wizard/);
});

// ===========================================================================
// API Key Manager (N-63)
// ===========================================================================

test('API Keys: renders heading and lists existing keys', async ({ page }) => {
  await gotoWithAuth(page, '/api-keys', { '**/auth/api-keys': PAGED_KEYS });
  await expect(page.getByTestId('page-title')).toBeVisible({ timeout: 15000 });
  await expect(page.getByTestId('keys-table')).toBeVisible();
  await expect(page.getByText('Production Key')).toBeVisible();
  await expect(page.getByText('Dev Key')).toBeVisible();
});

test('API Keys: creates a new key and reveals full value', async ({ page }) => {
  const createResp = { id: 'key-new', name: 'New Key', api_key: 'sk-newkey-full-value', key_prefix: 'sk-***new', is_active: true, created_at: 1711065600, last_used_at: null };
  await gotoWithAuth(page, '/api-keys', { '**/auth/api-keys': PAGED_KEYS });
  await page.route('**/auth/api-keys', async (route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify(createResp) });
      return;
    }
    await route.fallback();
  });
  await page.getByTestId('page-title').waitFor({ timeout: 15000 });
  await page.getByTestId('key-name-input').fill('New Key');
  await page.getByTestId('create-btn').click();
  await expect(page.getByTestId('revealed-key-value')).toBeVisible({ timeout: 5000 });
  await expect(page.getByTestId('revealed-key-value')).toContainText('sk-newkey-full-value');
});

test('API Keys: shows copy button on newly created key', async ({ page }) => {
  const createResp = { id: 'key-new', name: 'New Key', api_key: 'sk-newkey-full-value', key_prefix: 'sk-***new', is_active: true, created_at: 1711065600, last_used_at: null };
  await gotoWithAuth(page, '/api-keys', { '**/auth/api-keys': PAGED_KEYS });
  await page.route('**/auth/api-keys', async (route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify(createResp) });
      return;
    }
    await route.fallback();
  });
  await page.getByTestId('page-title').waitFor({ timeout: 15000 });
  await page.getByTestId('key-name-input').fill('New Key');
  await page.getByTestId('create-btn').click();
  await expect(page.getByTestId('copy-key-btn')).toBeVisible({ timeout: 5000 });
});

test('API Keys: revoke requires confirmation', async ({ page }) => {
  await gotoWithAuth(page, '/api-keys', { '**/auth/api-keys': PAGED_KEYS });
  await page.getByTestId('page-title').waitFor({ timeout: 15000 });
  await page.getByTestId('delete-btn').first().click();
  await expect(page.getByTestId('confirm-delete-btn')).toBeVisible();
});

test('API Keys: cancels revoke on No', async ({ page }) => {
  await gotoWithAuth(page, '/api-keys', { '**/auth/api-keys': PAGED_KEYS });
  await page.getByTestId('page-title').waitFor({ timeout: 15000 });
  await page.getByTestId('delete-btn').first().click();
  await page.getByTestId('cancel-delete-btn').click();
  await expect(page.getByTestId('delete-btn').first()).toBeVisible();
});

test('API Keys: accessible via nav link', async ({ page }) => {
  await gotoWithAuth(page, '/dashboard');
  await page.getByRole('link', { name: /API Keys/ }).click();
  await expect(page).toHaveURL(/\/api-keys/);
});

// ===========================================================================
// Node Config Demo Page (N-61 — SchemaForm)
// ===========================================================================

test('Node Config: renders page with JSON preview', async ({ page }) => {
  await gotoWithAuth(page, '/node-config');
  await expect(page.getByTestId('json-preview')).toBeVisible({ timeout: 15000 });
});

test('Node Config: has Save Config and Reset buttons', async ({ page }) => {
  await gotoWithAuth(page, '/node-config');
  await expect(page.getByRole('button', { name: 'Save Config' })).toBeVisible({ timeout: 15000 });
  await expect(page.getByRole('button', { name: 'Reset' })).toBeVisible();
});

test('Node Config: accessible via nav link', async ({ page }) => {
  await gotoWithAuth(page, '/dashboard');
  await page.getByRole('link', { name: /Node Config/ }).click();
  await expect(page).toHaveURL(/\/node-config/);
});
