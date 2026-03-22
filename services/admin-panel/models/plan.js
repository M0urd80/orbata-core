import { DataTypes } from 'sequelize'
import { sequelize } from './db.js'

export const Plan = sequelize.define(
  'Plan',
  {
    id: {
      type: DataTypes.UUID,
      primaryKey: true,
      defaultValue: DataTypes.UUIDV4,
    },
    name: { type: DataTypes.STRING(255), allowNull: false, unique: true },
    price: { type: DataTypes.DOUBLE, allowNull: false, defaultValue: 0 },
    created_at: {
      type: DataTypes.DATE,
      allowNull: false,
      defaultValue: DataTypes.NOW,
    },
  },
  {
    tableName: 'plans',
    timestamps: false,
    freezeTableName: true,
  }
)
