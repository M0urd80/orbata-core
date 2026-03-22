import { Sequelize } from 'sequelize'

/** Admin maps existing FastAPI tables only — no sync; names must match DB exactly. */
const defineDefaults = {
  underscored: true,
  freezeTableName: true,
}

const sequelizeOptions = {
  dialect: 'postgres',
  logging: false,
  define: defineDefaults,
}

/**
 * SQLAlchemy uses e.g. postgresql+psycopg:// — Sequelize/node-pg need postgres:// or postgresql://.
 */
function normalizePostgresUrlForSequelize(url) {
  if (!url || typeof url !== 'string') return url
  const trimmed = url.trim()
  // postgresql+driver:// → postgres://
  const sqlalchemyStyle = /^postgresql\+[^/]+:\/\//i
  if (sqlalchemyStyle.test(trimmed)) {
    return trimmed.replace(sqlalchemyStyle, 'postgres://')
  }
  return trimmed
}

/**
 * Same DB as core-auth: user `orbata`, database `orbata`, host `postgres` in Compose.
 * ADMIN_DATABASE_URL wins so .env can keep a SQLAlchemy-only DATABASE_URL without breaking Node.
 */
const rawDatabaseUrl =
  process.env.ADMIN_DATABASE_URL?.trim() ||
  process.env.DATABASE_URL?.trim() ||
  null
const databaseUrl = rawDatabaseUrl
  ? normalizePostgresUrlForSequelize(rawDatabaseUrl)
  : null

/**
 * Single Sequelize instance — all models import `sequelize` from here only.
 * Tables are owned by FastAPI; never call sequelize.sync() / force.
 */
export const sequelize = databaseUrl
  ? new Sequelize(databaseUrl, sequelizeOptions)
  : new Sequelize(
      process.env.POSTGRES_DB || 'orbata',
      process.env.POSTGRES_USER || 'orbata',
      process.env.POSTGRES_PASSWORD || 'orbata',
      {
        host: process.env.POSTGRES_HOST || 'postgres',
        ...sequelizeOptions,
      }
    )
