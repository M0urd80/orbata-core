import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { ComponentLoader } from 'adminjs'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

export const componentLoader = new ComponentLoader()

/** Bundled list UI for plan_quotas (grouped by package). */
export const PLAN_QUOTA_LIST_COMPONENT = componentLoader.add(
  'PlanQuotaList',
  path.join(__dirname, 'components', 'PlanQuotaList.jsx')
)
