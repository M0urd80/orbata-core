import { DataTypes } from 'sequelize'
import { sequelize } from './db.js'

export const Quota = sequelize.define(
  'Quota',
  {
    id: {
      type: DataTypes.UUID,
      primaryKey: true,
      defaultValue: DataTypes.UUIDV4,
    },
    service_id: { type: DataTypes.UUID, allowNull: false },
    name: {
      type: DataTypes.STRING(255),
      allowNull: false,
      defaultValue: '',
    },
    quota_daily: { type: DataTypes.INTEGER, allowNull: false, defaultValue: 0 },
    quota_monthly: { type: DataTypes.INTEGER, allowNull: false, defaultValue: 0 },
    created_at: {
      type: DataTypes.DATE,
      allowNull: false,
      defaultValue: DataTypes.NOW,
    },
  },
  {
    tableName: 'quotas',
    timestamps: false,
    freezeTableName: true,
  }
)
