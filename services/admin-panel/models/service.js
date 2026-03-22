import { DataTypes } from 'sequelize'
import { sequelize } from './db.js'

export const Service = sequelize.define(
  'Service',
  {
    id: {
      type: DataTypes.UUID,
      primaryKey: true,
      defaultValue: DataTypes.UUIDV4,
    },
    name: { type: DataTypes.STRING(64), allowNull: false, unique: true },
    description: { type: DataTypes.STRING(512), allowNull: true },
    created_at: {
      type: DataTypes.DATE,
      allowNull: false,
      defaultValue: DataTypes.NOW,
    },
  },
  {
    tableName: 'services',
    timestamps: false,
    freezeTableName: true,
  }
)
