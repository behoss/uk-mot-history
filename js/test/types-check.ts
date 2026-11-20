// Compile-only check that the published types fit real usage (run by `npm run typecheck`).
import { MotHistoryClient, findMileageAnomalies, motExpiry, type Vehicle } from "../src/index.js";

async function demo(env: Record<string, string | undefined>): Promise<string> {
  const client = MotHistoryClient.fromEnv(env);
  const vehicle: Vehicle = await client.byRegistration("AB12CDE");
  const drops = findMileageAnomalies(vehicle).map((a) => `${a.drop} miles on ${a.later.date}`);
  return `${vehicle.make} ${vehicle.model}: MOT to ${motExpiry(vehicle) ?? "?"}; ${drops.join(", ") || "no drops"}`;
}
void demo;
