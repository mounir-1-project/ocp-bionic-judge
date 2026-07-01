/**
 * Shared application-level constants.
 * `as const` gives literal types — MachineId / SensorKey are derived from the arrays,
 * so adding a machine here automatically propagates the type everywhere.
 */

export const MACHINES = [
  'BROYEUR_01',
  'POMPE_02',
  'CONVOYEUR_03',
  'REACTEUR_04',
  'COMPRESSEUR_05',
] as const

export type MachineId = typeof MACHINES[number]

export const M_NAMES: Record<MachineId, string> = {
  BROYEUR_01:    'Broyeur à Boulets',
  POMPE_02:      'Pompe Centrifuge',
  CONVOYEUR_03:  'Convoyeur à Courroie',
  REACTEUR_04:   "Réacteur d'Attaque",
  COMPRESSEUR_05:'Compresseur Industriel',
}

export const SENSORS = ['temperature', 'vibration', 'pression', 'courant', 'rpm'] as const
export type SensorKey = typeof SENSORS[number]

export const S_UNITS: Record<SensorKey, string> = {
  temperature: '°C',
  vibration:   'mm/s',
  pression:    'bar',
  courant:     'A',
  rpm:         'tr/min',
}
