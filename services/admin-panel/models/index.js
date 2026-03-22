/**
 * Load all Sequelize models + associations before AdminJS.
 * Schema is owned by core-auth (SQLAlchemy) — this service never calls sequelize.sync().
 * Import order: db → models → associations (side effects).
 */
export { sequelize } from './db.js'
export { Plan } from './plan.js'
export { Service } from './service.js'
export { Quota } from './quota.js'
export { PlanQuota } from './planQuota.js'
export { Client } from './client.js'
export { Usage } from './usage.js'
export { EmailLog } from './emailLog.js'

import './associations.js'
