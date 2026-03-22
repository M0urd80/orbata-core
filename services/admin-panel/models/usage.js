import { DataTypes } from 'sequelize'
import { sequelize } from './db.js'

export const Usage = sequelize.define(
  'Usage',
  {
    id: {
      type: DataTypes.UUID,
      primaryKey: true,
      defaultValue: DataTypes.UUIDV4,
    },
    client_id: { type: DataTypes.UUID, allowNull: false },
    date: { type: DataTypes.DATEONLY, allowNull: false },
    service_id: { type: DataTypes.UUID, allowNull: false },
    sent_count: { type: DataTypes.INTEGER, allowNull: false, defaultValue: 0 },
    success_count: { type: DataTypes.INTEGER, allowNull: false, defaultValue: 0 },
    fail_count: { type: DataTypes.INTEGER, allowNull: false, defaultValue: 0 },
  },
  {
    tableName: 'usage',
    timestamps: false,
    freezeTableName: true,
  }
)
