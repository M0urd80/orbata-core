import { DataTypes } from 'sequelize'
import { sequelize } from './db.js'

export const EmailLog = sequelize.define(
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
    created_at: {
      type: DataTypes.DATE,
      allowNull: false,
      defaultValue: DataTypes.NOW,
    },
  },
  {
    tableName: 'email_logs',
    timestamps: false,
    freezeTableName: true,
  }
)
