import crypto from 'node:crypto'
import express from 'express'
import session from 'express-session'
import RedisStore from 'connect-redis'
import { createClient } from 'redis'
import { Op } from 'sequelize'
import AdminJS from 'adminjs'
import AdminJSExpress from '@adminjs/express'
import * as AdminJSSequelize from '@adminjs/sequelize'
import {
  componentLoader,
  PLAN_QUOTA_LIST_COMPONENT,
} from './component-loader.js'
/**
 * Always import models from `./models/index.js` — one shared `sequelize` (`db.js`) and associations loaded.
 * Do not default-import `./models/plan.js` etc. in the app entrypoint or you risk a second connection / missing relations.
 */
import {
  sequelize,
  Plan,
  Service,
  Quota,
  PlanQuota,
  Client,
  Usage,
  EmailLog,
} from './models/index.js'

/** Required for @adminjs/sequelize — without this, FK reference dropdowns do not work. */
AdminJS.registerAdapter({
  Resource: AdminJSSequelize.Resource,
  Database: AdminJSSequelize.Database,
})

const PORT = Number(process.env.PORT) || 3000
const NODE_ENV = process.env.NODE_ENV || 'development'

/** Optional: auto-set `plan_id` on new Client when Admin leaves plan empty (UUID string). */
const DEFAULT_CLIENT_PLAN_ID = process.env.DEFAULT_CLIENT_PLAN_ID?.trim() || ''

/** Match core-auth `hash_api_key` (SHA-256 hex of UTF-8 secret). */
function hashApiKeyForStorage(rawSecret) {
  return crypto.createHash('sha256').update(String(rawSecret), 'utf8').digest('hex')
}

/**
 * AdminJS encrypted cookie vs express-session secret.
 * Set both in production. If only one is set, we fall back so session + cookie stay aligned (avoids redirect loops).
 */
const ADMINJS_COOKIE_PASSWORD =
  process.env.ADMINJS_COOKIE_SECRET ||
  process.env.ADMINJS_COOKIE_PASSWORD ||
  'change-me-adminjs-cookie'

const ADMINJS_SESSION_SECRET_VALUE =
  process.env.ADMINJS_SESSION_SECRET ||
  process.env.ADMINJS_COOKIE_SECRET ||
  ADMINJS_COOKIE_PASSWORD

const REDIS_HOST = process.env.REDIS_HOST || 'redis'
const REDIS_PORT = Number(process.env.REDIS_PORT) || 6379

/** Delay between Sequelize `authenticate()` attempts while Postgres starts (Compose). */
const DB_RETRY_DELAY_MS = Number(process.env.DB_RETRY_DELAY_MS) || 2000
const REDIS_MAX_RETRIES = Number(process.env.REDIS_MAX_RETRIES) || 10
const REDIS_RETRY_DELAY_MS = Number(process.env.REDIS_RETRY_DELAY_MS) || 2000

const readOnlyId = { isDisabled: true }

const datetimeProp = { type: 'datetime' }

const dateOnlyProp = { type: 'date' }

/** Hide column until product uses key expiration in UI. */
const hiddenExpiresAt = {
  isVisible: {
    list: false,
    show: false,
    filter: false,
    edit: false,
    new: false,
  },
}

/** System timestamps: DB default NOW(); never editable in AdminJS. */
const createdAtReadonly = {
  ...datetimeProp,
  isVisible: {
    list: true,
    show: true,
    edit: false,
    filter: true,
    new: false,
  },
  isEditable: false,
}

/** Sidebar groups (parent `name` must match to nest under same section). */
const nav = {
  core: { name: 'Core', icon: 'Box' },
  packages: { name: 'Packages', icon: 'Package' },
  configuration: { name: 'Configuration', icon: 'Settings' },
  monitoring: { name: 'Monitoring', icon: 'Activity' },
}

/** AdminJS reference fields may be UUID strings or `{ id }` objects. */
function resolveFkId(val) {
  if (val == null || val === '') return null
  if (typeof val === 'object' && val !== null) {
    if (val.id != null) return String(val.id)
    if (val.value != null) return String(val.value)
  }
  return String(val)
}

/** Block duplicate (plan_id, quota_id); DB also enforces UNIQUE. */
async function assertUniquePlanQuotaLink(request, { editingId } = {}) {
  const payload = request.payload
  if (!payload) return request

  let planId = resolveFkId(payload.plan_id)
  let quotaId = resolveFkId(payload.quota_id)
  if (editingId && (planId === undefined || quotaId === undefined)) {
    const row = await PlanQuota.findByPk(editingId)
    if (row) {
      if (planId === undefined || planId === '') planId = row.plan_id
      if (quotaId === undefined || quotaId === '') quotaId = row.quota_id
    }
  }
  if (!planId || !quotaId) return request

  const dup = await PlanQuota.findOne({
    where: {
      plan_id: planId,
      quota_id: quotaId,
      ...(editingId ? { id: { [Op.ne]: editingId } } : {}),
    },
  })
  if (dup) {
    throw new Error('This quota is already linked to this package.')
  }
  return request
}

/**
 * Monthly = daily × 30; name = SERVICE-NNN/day (matches core-auth SQLAlchemy).
 * At most one linked quota per channel per package is enforced separately.
 */
async function syncQuotaDerivedFromPayload(request, { editingId } = {}) {
  const p = request.payload
  if (!p) return request
  let sid = resolveFkId(p.service_id)
  let daily = p.quota_daily
  if (
    editingId &&
    (sid === undefined ||
      sid === '' ||
      sid === null ||
      daily === undefined ||
      daily === '')
  ) {
    const row = await Quota.findByPk(editingId)
    if (row) {
      if (sid === undefined || sid === '' || sid === null)
        sid = row.service_id
      if (daily === undefined || daily === '') daily = row.quota_daily
    }
  }
  const d = Math.trunc(Number(daily ?? 0))
  if (!sid) return request
  const svc = await Service.findByPk(sid)
  if (!svc) return request
  p.service_id = sid
  p.quota_daily = d
  p.quota_monthly = d * 30
  p.name = `${String(svc.name).toUpperCase()}-${d}/day`
  return request
}

async function assertOneChannelQuotaPerPackage(request, { editingId } = {}) {
  const payload = request.payload
  const qid = resolveFkId(payload?.quota_id)
  const pid = resolveFkId(payload?.plan_id)
  if (!pid || !qid) return request
  const quota = await Quota.findByPk(qid)
  if (!quota) return request
  const siblings = await PlanQuota.findAll({
    where: { plan_id: pid },
  })
  for (const pq of siblings) {
    if (editingId && String(pq.id) === String(editingId)) continue
    const other = await Quota.findByPk(pq.quota_id)
    if (other && String(other.service_id) === String(quota.service_id)) {
      throw new Error('This package already has a quota for this channel.')
    }
  }
  return request
}

async function assertNotLastQuotaForPackage(recordId) {
  const row = await PlanQuota.findByPk(recordId)
  if (!row) return
  const n = await PlanQuota.count({ where: { plan_id: row.plan_id } })
  if (n <= 1) {
    throw new Error(
      'Each package must keep at least one service quota. Add another quota for this package before deleting this row.'
    )
  }
}

/**
 * Sequelize relations load at import. AdminJS is created in `main()` after DB + `public.plans` exist.
 * `reference` values MUST match Sequelize `tableName` (`plans`, `services`).
 * Register Plan, Service, Quota before PlanQuota, Client, Usage (FK dropdowns).
 */
function createAdminInstance() {
  return new AdminJS({
    componentLoader,
    databases: [new AdminJSSequelize.Database(sequelize)],
    rootPath: '/admin',
    branding: {
      companyName: 'Orbata Core',
      softwareBrothers: false,
    },
    resources: [
      {
        resource: Plan,
        options: {
          titleProperty: 'name',
          navigation: {
            name: 'Tiers',
            icon: 'Tag',
            parent: nav.packages,
          },
          description:
            'Product packages (e.g. Free, Pro). Define **Quotas** (channel + limits), then link them under **Package quotas**.',
          listProperties: ['name', 'price', 'created_at'],
          showProperties: ['id', 'name', 'price', 'created_at'],
          editProperties: ['name', 'price'],
          newProperties: ['name', 'price'],
          properties: {
            id: readOnlyId,
            name: {
              isTitle: true,
              label: 'Package name',
              description: 'Shown in admin and APIs (e.g. Free, Pro, Enterprise).',
            },
            price: {
              type: 'number',
              label: 'Price',
            },
            created_at: createdAtReadonly,
          },
        },
      },
      {
        resource: Service,
        options: {
          titleProperty: 'name',
          navigation: {
            name: 'Services',
            icon: 'Radio',
            parent: nav.configuration,
          },
          properties: {
            id: readOnlyId,
            created_at: createdAtReadonly,
          },
        },
      },
      {
        resource: Client,
        options: {
          navigation: {
            name: 'Clients',
            icon: 'User',
            parent: nav.core,
          },
          actions: {
            new: {
              before: async (request) => {
                if (request.payload) {
                  const rawKey = `orb_live_${crypto.randomBytes(32).toString('hex')}`
                  request.payload.api_key = hashApiKeyForStorage(rawKey)
                  if (!request.payload.plan_id) {
                    if (DEFAULT_CLIENT_PLAN_ID) {
                      request.payload.plan_id = DEFAULT_CLIENT_PLAN_ID
                    } else {
                      const free = await Plan.findOne({ where: { name: 'Free' } })
                      if (free) request.payload.plan_id = free.id
                    }
                  }
                  if (
                    request.payload.is_active === undefined ||
                    request.payload.is_active === null
                  ) {
                    request.payload.is_active = true
                  }
                  delete request.payload.created_at
                }
                return request
              },
            },
          },
          properties: {
            id: readOnlyId,
            plan_id: {
              reference: 'plans',
              isRequired: true,
              label: 'Package',
              description:
                'Billing package; limits come from **Package quotas** → **Quotas** (per channel), not this row.',
            },
            api_key: {
              isVisible: {
                list: false,
                show: true,
                filter: false,
                edit: false,
                new: false,
              },
              description:
                'Auto-generated on create (SHA-256 in DB). Rotate via admin API for a new raw key.',
            },
            created_at: createdAtReadonly,
            expires_at: hiddenExpiresAt,
            rotated_at: { ...datetimeProp, label: 'Last Key Rotation' },
          },
        },
      },
      {
        resource: Quota,
        options: {
          navigation: {
            name: 'Quotas',
            icon: 'Sliders',
            parent: nav.packages,
          },
          titleProperty: 'name',
          description:
            'Set **channel** + **daily** only. Monthly = daily × 30 and **name** (e.g. EMAIL-200/day) are generated automatically.',
          sort: {
            sortBy: 'created_at',
            direction: 'desc',
          },
          listProperties: [
            'name',
            'service_id',
            'quota_daily',
            'quota_monthly',
            'created_at',
          ],
          showProperties: [
            'id',
            'name',
            'service_id',
            'quota_daily',
            'quota_monthly',
            'created_at',
          ],
          editProperties: ['service_id', 'quota_daily'],
          newProperties: ['service_id', 'quota_daily'],
          filterProperties: ['service_id'],
          actions: {
            new: {
              before: async (request) => {
                await syncQuotaDerivedFromPayload(request)
                return request
              },
            },
            edit: {
              before: async (request) => {
                const id =
                  request.params?.recordId ?? request.payload?.id
                await syncQuotaDerivedFromPayload(request, {
                  editingId: id,
                })
                return request
              },
            },
          },
          properties: {
            id: readOnlyId,
            name: {
              isTitle: true,
              label: 'Quota label',
              isVisible: {
                list: true,
                show: true,
                edit: false,
                filter: true,
                new: false,
              },
              description: 'Auto: CHANNEL-daily/day',
            },
            service_id: {
              reference: 'services',
              label: 'Channel',
              description: 'e.g. email, sms, whatsapp',
            },
            quota_daily: {
              type: 'number',
              label: 'Daily limit',
              description: '0 = unlimited (per UTC day). Monthly = this × 30.',
            },
            quota_monthly: {
              type: 'number',
              label: 'Monthly limit (auto)',
              isVisible: {
                list: true,
                show: true,
                edit: false,
                filter: false,
                new: false,
              },
              description: 'Always daily × 30 — not editable.',
            },
            created_at: createdAtReadonly,
          },
        },
      },
      {
        resource: PlanQuota,
        options: {
          navigation: {
            name: 'Package quotas',
            icon: 'Layers',
            parent: nav.packages,
          },
          description:
            'Attach predefined **Quotas** to a **Package**. One link per (package, quota). Limits are edited only on the Quota record.',
          sort: {
            sortBy: 'plan_id',
            direction: 'asc',
          },
          listProperties: ['plan_id', 'quota_id'],
          showProperties: ['plan_id', 'quota_id'],
          editProperties: ['plan_id', 'quota_id'],
          newProperties: ['plan_id', 'quota_id'],
          filterProperties: ['plan_id', 'quota_id'],
          actions: {
            list: {
              component: PLAN_QUOTA_LIST_COMPONENT,
            },
            bulkDelete: { isAccessible: false },
            new: {
              before: async (request) => {
                await assertUniquePlanQuotaLink(request)
                await assertOneChannelQuotaPerPackage(request)
                return request
              },
            },
            edit: {
              before: async (request) => {
                const id =
                  request.params?.recordId ?? request.payload?.id
                if (id) {
                  await assertUniquePlanQuotaLink(request, {
                    editingId: id,
                  })
                  await assertOneChannelQuotaPerPackage(request, {
                    editingId: id,
                  })
                }
                return request
              },
            },
            delete: {
              before: async (request) => {
                const id = request.params?.recordId
                if (id) await assertNotLastQuotaForPackage(id)
                return request
              },
            },
          },
          properties: {
            id: {
              isVisible: {
                list: false,
                show: false,
                filter: false,
                edit: false,
                new: false,
              },
            },
            plan_id: {
              reference: 'plans',
              isTitle: true,
              label: 'Package',
              description: 'Create the tier under **Tiers** first.',
            },
            quota_id: {
              reference: 'quotas',
              label: 'Quota',
              description:
                'Choose a quota definition (shows channel via service). Same quota can power multiple packages.',
            },
          },
        },
      },
      {
        resource: EmailLog,
        options: {
          navigation: {
            name: 'Logs',
            icon: 'Email',
            parent: nav.monitoring,
          },
          properties: {
            created_at: createdAtReadonly,
          },
        },
      },
      {
        resource: Usage,
        options: {
          navigation: {
            name: 'Usage',
            icon: 'BarChart',
            parent: nav.monitoring,
          },
          properties: {
            date: dateOnlyProp,
            service_id: {
              reference: 'services',
              label: 'Service',
              isVisible: true,
            },
          },
        },
      },
    ],
  })
}

const app = express()
app.set('trust proxy', 1)

app.get('/health', (_req, res) => {
  res.json({ status: 'ok', env: NODE_ENV })
})

/**
 * Wait until Postgres accepts connections (no max attempts — survives slow `compose up`).
 * Run this before any Sequelize queries.
 */
async function waitForDb() {
  let connected = false
  let attempt = 0
  while (!connected) {
    attempt += 1
    try {
      await sequelize.authenticate()
      connected = true
      const c = sequelize.config
      console.log('✅ DB ready')
      console.log(
        `[admin-panel] DB: ${c.database} @ ${c.host}:${c.port ?? 5432} (user: ${c.username}) — expect orbata@postgres, not empty default DB`
      )
    } catch (e) {
      console.log(
        `⏳ Waiting for DB… (attempt ${attempt}):`,
        e?.message || e
      )
      await new Promise((r) => setTimeout(r, DB_RETRY_DELAY_MS))
    }
  }
}

/**
 * `depends_on` does not wait for core-auth to finish creating tables — poll until `plans` exists.
 */
async function waitForTables() {
  let ready = false
  while (!ready) {
    try {
      const [rows] = await sequelize.query(
        `SELECT to_regclass('public.plans') AS plan_table;`
      )
      const reg = rows[0]?.plan_table
      if (reg != null && reg !== '') {
        console.log('✅ Tables exist')
        ready = true
      } else {
        throw new Error('Tables not ready')
      }
    } catch {
      console.log('⏳ Waiting for tables...')
      await new Promise((r) => setTimeout(r, DB_RETRY_DELAY_MS))
    }
  }
}

async function connectRedisWithRetry() {
  const url = `redis://${REDIS_HOST}:${REDIS_PORT}`
  const client = createClient({ url })
  client.on('error', (err) => {
    console.error('Redis (session) client error:', err.message)
  })

  for (let attempt = 1; attempt <= REDIS_MAX_RETRIES; attempt++) {
    try {
      await client.connect()
      console.log('Redis session store OK:', url)
      return client
    } catch (err) {
      console.warn(
        `Redis not ready, retry ${attempt}/${REDIS_MAX_RETRIES}:`,
        err.message
      )
      if (attempt === REDIS_MAX_RETRIES) {
        throw err
      }
      await new Promise((r) => setTimeout(r, REDIS_RETRY_DELAY_MS))
    }
  }
}

async function main() {
  // Debug: values come from Compose `env_file` / `environment`, not from a .env file read by Node.
  // Confirm in container: docker exec -it orbata-core-admin-panel-1 printenv | grep ADMIN
  console.log('ENV:', process.env.ADMIN_USER, process.env.ADMIN_PASSWORD)

  await waitForDb()
  await waitForTables()

  const admin = createAdminInstance()
  console.log(
    '[admin-panel] resource tableNames:',
    admin.options.resources.map((r) => r.resource?.model?.tableName)
  )
  console.log('AdminJS started')

  let redisClient
  try {
    redisClient = await connectRedisWithRetry()
  } catch (err) {
    console.error('Redis connection failed after retries:', err.message)
    process.exit(1)
  }

  const redisStore = new RedisStore({
    client: redisClient,
    prefix: 'orbata:admin:sess:',
  })

  /**
   * Global session — same `secret` + `store` as AdminJS router below (required or sessions won’t stick).
   */
  const sessionOptions = {
    store: redisStore,
    secret: ADMINJS_SESSION_SECRET_VALUE,
    resave: false,
    saveUninitialized: true,
    cookie: {
      secure: false,
      httpOnly: true,
      sameSite: 'lax',
    },
  }

  app.use(session(sessionOptions))

  const router = AdminJSExpress.buildAuthenticatedRouter(
    admin,
    {
      authenticate: async (email, password) => {
        if (
          email === process.env.ADMIN_USER &&
          password === process.env.ADMIN_PASSWORD
        ) {
          return { email }
        }
        return null
      },
      cookieName: 'adminjs',
      cookiePassword: ADMINJS_COOKIE_PASSWORD,
    },
    null,
    {
      ...sessionOptions,
    }
  )

  app.use(admin.options.rootPath, router)

  app.listen(PORT, '0.0.0.0', () => {
    console.log(
      `AdminJS: http://localhost:${PORT}${admin.options.rootPath} (NODE_ENV=${NODE_ENV})`
    )
    console.log('Sessions: Redis store | Set ADMIN_USER / ADMIN_PASSWORD in env.')
  })
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
