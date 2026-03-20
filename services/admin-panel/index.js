import express from 'express'
import session from 'express-session'
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

const DB_MAX_RETRIES = Number(process.env.DB_MAX_RETRIES) || 10
const DB_RETRY_DELAY_MS = Number(process.env.DB_RETRY_DELAY_MS) || 2000

const sequelize = new Sequelize(POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD, {
  host: POSTGRES_HOST,
  dialect: 'postgres',
  logging: false,
  define: {
    underscored: true,
    timestamps: false,
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
  { tableName: 'clients' }
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
  { tableName: 'email_logs' }
)

AdminJS.registerAdapter({
  Resource: AdminJSSequelize.Resource,
  Database: AdminJSSequelize.Database,
})

const hiddenApiKey = {
  isVisible: {
    list: false,
    show: false,
    filter: false,
    edit: false,
  },
}

const admin = new AdminJS({
  databases: [new AdminJSSequelize.Database(sequelize)],
  resources: [
    {
      resource: Client,
      options: {
        navigation: {
          name: 'Clients',
          icon: 'User',
          parent: {
            name: 'Core',
            icon: 'Settings',
          },
        },
        properties: {
          api_key: hiddenApiKey,
        },
      },
    },
    {
      resource: EmailLog,
      options: {
        navigation: {
          name: 'Email Logs',
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
        filterProperties: ['status', 'client_id', 'email'],
        showProperties: [
          'id',
          'client_id',
          'email',
          'status',
          'attempts',
          'error_message',
          'created_at',
        ],
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

/**
 * Session must match AdminJS `cookiePassword` (`supersecretcookie`).
 * After changing secrets, clear cookies for localhost:3000 or use Incognito.
 */
app.use(
  session({
    secret: 'supersecretcookie',
    resave: true,
    saveUninitialized: true,
    cookie: {
      secure: false, // IMPORTANT for HTTP (dev)
      httpOnly: true,
      sameSite: 'lax', // critical for login flow
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

async function main() {
  try {
    await connectPostgresWithRetry()
  } catch (err) {
    console.error('Postgres connection failed after retries:', err.message)
    process.exit(1)
  }

  app.listen(PORT, '0.0.0.0', () => {
    console.log(
      `AdminJS: http://localhost:${PORT}${admin.options.rootPath} (NODE_ENV=${NODE_ENV})`
    )
    console.log('Set ADMIN_USER / ADMIN_PASSWORD in environment (never defaults in prod).')
  })
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
