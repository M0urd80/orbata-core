import { DataTypes } from 'sequelize'
import { sequelize } from './db.js'

export const Client = sequelize.define(
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
    is_active: { type: DataTypes.BOOLEAN, allowNull: false, defaultValue: true },
    created_at: {
      type: DataTypes.DATE,
      allowNull: false,
      defaultValue: DataTypes.NOW,
    },
    expires_at: { type: DataTypes.DATE, allowNull: true },
    rotated_at: { type: DataTypes.DATE, allowNull: true },
    plan_id: { type: DataTypes.UUID, allowNull: false },
  },
  {
    tableName: 'clients',
    timestamps: false,
    freezeTableName: true,
  }
)
