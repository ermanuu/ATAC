type PositionAge = {
  timestamp: number;
  retained?: boolean;
  positionSource?: string;
  predictionTimestamp?: number | null;
};

// A failed poll or an omitted vehicle must not erase recent location evidence.
// Keep its original clock and label it last-known; never extend its lifetime.
export function visibleVehicles<T extends PositionAge>(vehicles: T[], now: number, requestFailed = false): T[] {
  return vehicles.filter(vehicle => {
    const age = now - vehicle.timestamp;
    const predictionAge = now - (vehicle.predictionTimestamp ?? 0);
    return age >= 0 && age <= 180 && (vehicle.positionSource !== 'predictions' ||
      Boolean(vehicle.predictionTimestamp && predictionAge >= 0 && predictionAge <= 180));
  }).map(vehicle => requestFailed || now - vehicle.timestamp > 90
    ? { ...vehicle, retained: true }
    : vehicle);
}
