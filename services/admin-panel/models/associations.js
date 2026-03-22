/**
 * Required for AdminJS reference dropdowns (FK UIs).
 * Load from models/index.js before AdminJS.
 */
import { Plan } from './plan.js'
import { Service } from './service.js'
import { Quota } from './quota.js'
import { PlanQuota } from './planQuota.js'
import { Client } from './client.js'
import { Usage } from './usage.js'

Quota.belongsTo(Service, { foreignKey: 'service_id' })
Service.hasMany(Quota, { foreignKey: 'service_id' })

PlanQuota.belongsTo(Plan, { foreignKey: 'plan_id' })
PlanQuota.belongsTo(Quota, { foreignKey: 'quota_id' })

Plan.hasMany(PlanQuota, { foreignKey: 'plan_id' })
Quota.hasMany(PlanQuota, { foreignKey: 'quota_id' })

Plan.hasMany(Client, { foreignKey: 'plan_id' })
Client.belongsTo(Plan, { foreignKey: 'plan_id' })

Service.hasMany(Usage, { foreignKey: 'service_id' })
Usage.belongsTo(Service, { foreignKey: 'service_id' })
