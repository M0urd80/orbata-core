import { DataTypes } from 'sequelize'
import { sequelize } from './db.js'

export const PlanQuota = sequelize.define(
  'PlanQuota',
  {
    id: {
      type: DataTypes.UUID,
      primaryKey: true,
      defaultValue: DataTypes.UUIDV4,
    },
    plan_id: { type: DataTypes.UUID, allowNull: false },
    quota_id: { type: DataTypes.UUID, allowNull: false },
  },
  {
    tableName: 'plan_quotas',
    timestamps: false,
    freezeTableName: true,
    indexes: [
      {
        unique: true,
        fields: ['plan_id', 'quota_id'],
        name: 'uq_plan_quota_plan_quota_id',
      },
    ],
  }
)
