import express from 'express'
import session from 'express-session'
import RedisStore from 'connect-redis'
import { createClient } from 'redis'
import AdminJS from 'adminjs'
import AdminJSExpress from '@adminjs/express'
import AdminJSSequelize from '@adminjs/sequelize'
import { Sequelize, DataTypes } from 'sequelize'

const PORT = Number(process.env.PORT) || 3000
const NODE_ENV = process.env.NODE_ENV || 'development'

const POSTGRES_HOST = process.env.POSTGRES_HOST || 'postgres'
const POSTGRES_DB = process.env.POSTGRES_DB || 'orbata'
const POSTGRES_USER = process.env.POSTGRES_USER || 'orbata'
const POSTGRES_PASSWORD = process.env.POSTGRES_PASSWORD || 'orbata'

const REDIS_HOST = process.env.REDIS_HOST || 'redis'
const REDIS_PORT = Number(process.env.REDIS_PORT) || 6379

const DB_MAX_RETRIES = Number(process.env.DB_MAX_RETRIES) || 10
const DB_RETRY_DELAY_MS = Number(process.env.DB_RETRY_DELAY_MS) || 2000
const REDIS_MAX_RETRIES = Number(process.env.REDIS_MAX_RETRIES) || 10
const REDIS_RETRY_DELAY_MS = Number(process.env.REDIS_RETRY_DELAY_MS) || 2000

/**
 * Tables `clients` and `email_logs` are created by FastAPI (SQLAlchemy).
 * We only connect and map columns — never call sequelize.sync().
 */
const sequelize = new Sequelize(POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD, {
  host: POSTGRES_HOST,
  dialect: 'postgres',
  logging: false,
  define: {
    underscored: true,
  },
})

const Client = sequelize.define(
  'Client',
  {
    id: {
      type: DataTypes.UUID,
      primaryKey: true,
      defaultValue: DataTypes.UUIDV4,
    },
    name: { type: DataTypes.STRING(255), allowNull: false },
    email_from_name: { type: DataTypes.STRING(255), allowNull: true },
    api_key: { type: DataTypes.STRING(255), allowNull: false, unique: true },
    created_at: { type: DataTypes.DATE, allowNull: false },
    expires_at: { type: DataTypes.DATE, allowNull: true },
    rotated_at: { type: DataTypes.DATE, allowNull: true },
  },
  {
    tableName: 'clients',
    timestamps: false,
  }
)

const Usage = sequelize.define(
  'Usage',
  {
    id: {
      type: DataTypes.UUID,
      primaryKey: true,
      defaultValue: DataTypes.UUIDV4,
    },
    client_id: { type: DataTypes.UUID, allowNull: false },
    date: { type: DataTypes.DATEONLY, allowNull: false },
    channel: { type: DataTypes.STRING(32), allowNull: false },
    sent_count: { type: DataTypes.INTEGER, allowNull: false, defaultValue: 0 },
    success_count: { type: DataTypes.INTEGER, allowNull: false, defaultValue: 0 },
    fail_count: { type: DataTypes.INTEGER, allowNull: false, defaultValue: 0 },
  },
  {
    tableName: 'usage',
    timestamps: false,
  }
)

const EmailLog = sequelize.define(
  'EmailLog',
  {
    id: {
      type: DataTypes.UUID,
      primaryKey: true,
      defaultValue: DataTypes.UUIDV4,
    },
    client_id: { type: DataTypes.UUID, allowNull: false },
    email: { type: DataTypes.STRING(512), allowNull: false },
    status: { type: DataTypes.STRING(32), allowNull: false },
    attempts: { type: DataTypes.INTEGER, allowNull: false, defaultValue: 0 },
    error_message: { type: DataTypes.TEXT, allowNull: true },
    created_at: { type: DataTypes.DATE, allowNull: false },
  },
  {
    tableName: 'email_logs',
    timestamps: false,
  }
)

AdminJS.registerAdapter({
  Resource: AdminJSSequelize.Resource,
  Database: AdminJSSequelize.Database,
})

/** Never surface hashed API keys in the UI. */
const hiddenApiKey = {
  isVisible: {
    list: false,
    show: false,
    filter: false,
    edit: false,
    new: false,
  },
}

const readOnlyId = {
  isDisabled: true,
}

/** Hide column everywhere until product uses key expiration in UI. */
const hiddenExpiresAt = {
  isVisible: {
    list: false,
    show: false,
    filter: false,
    edit: false,
    new: false,
  },
}

/** AdminJS needs explicit datetime so list/show render timestamps correctly. */
const datetimeProp = {
  type: 'datetime',
}

const dateOnlyProp = {
  type: 'date',
}

const admin = new AdminJS({
  databases: [new AdminJSSequelize.Database(sequelize)],
  resources: [
    {
      resource: Client,
      options: {
        navigation: {
          name: 'Customers',
          icon: 'User',
          parent: {
            name: 'Core',
            icon: 'Settings',
          },
        },
        properties: {
          id: readOnlyId,
          api_key: hiddenApiKey,
          created_at: datetimeProp,
          expires_at: hiddenExpiresAt,
          rotated_at: {
            ...datetimeProp,
            label: 'Last Key Rotation',
          },
        },
      },
    },
    {
      resource: EmailLog,
      options: {
        navigation: {
          name: 'OTP Logs',
          icon: 'Email',
          parent: {
            name: 'Monitoring',
            icon: 'Activity',
          },
        },
        sort: {
          sortBy: 'created_at',
          direction: 'desc',
        },
        listProperties: ['email', 'status', 'attempts', 'created_at'],
        filterProperties: ['status', 'client_id'],
        searchProperties: ['email'],
        showProperties: [
          'id',
          'client_id',
          'email',
          'status',
          'attempts',
          'error_message',
          'created_at',
        ],
        properties: {
          created_at: datetimeProp,
        },
      },
    },
    {
      resource: Usage,
      options: {
        navigation: {
          name: 'Usage',
          icon: 'BarChart',
          parent: {
            name: 'Monitoring',
            icon: 'Activity',
          },
        },
        sort: {
          sortBy: 'date',
          direction: 'desc',
        },
        listProperties: [
          'client_id',
          'date',
          'sent_count',
          'success_count',
          'fail_count',
        ],
        filterProperties: ['client_id', 'date', 'channel'],
        showProperties: [
          'client_id',
          'date',
          'sent_count',
          'success_count',
          'fail_count',
        ],
        properties: {
          date: dateOnlyProp,
        },
      },
    },
  ],
  rootPath: '/admin',
  branding: {
    companyName: 'Orbata Core',
    softwareBrothers: false,
  },
})

const app = express()
app.set('trust proxy', 1)

app.get('/health', (_req, res) => {
  res.json({ status: 'ok', env: NODE_ENV })
})

async function connectPostgresWithRetry() {
  for (let attempt = 1; attempt <= DB_MAX_RETRIES; attempt++) {
    try {
      await sequelize.authenticate()
      console.log('Postgres connection OK')
      return
    } catch (err) {
      console.warn(
        `DB not ready, retry ${attempt}/${DB_MAX_RETRIES}:`,
        err.message
      )
      if (attempt === DB_MAX_RETRIES) {
        throw err
      }
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
  try {
    await connectPostgresWithRetry()
  } catch (err) {
    console.error('Postgres connection failed after retries:', err.message)
    process.exit(1)
  }

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
   * Session secret must match AdminJS `cookiePassword`.
   * Clear cookies for localhost:3000 after secret changes.
   */
  app.use(
    session({
      store: redisStore,
      secret: 'supersecretcookie',
      resave: true,
      saveUninitialized: true,
      cookie: {
        secure: false,
        httpOnly: true,
        sameSite: 'lax',
      },
    })
  )

  const router = AdminJSExpress.buildAuthenticatedRouter(
    admin,
    {
      authenticate: async (email, password) => {
        if (
          email === process.env.ADMIN_USER &&
          password === process.env.ADMIN_PASSWORD
        ) {
          console.log('AUTH SUCCESS')
          return { email }
        }
        return null
      },
      cookieName: 'adminjs',
      cookiePassword: 'supersecretcookie',
    },
    null,
    {
      resave: true,
      saveUninitialized: true,
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
