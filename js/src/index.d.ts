// Types for uk-mot-history (DVSA MOT History API, v1 trade endpoints).

export declare const API_BASE: string;
export declare const DEFAULT_SCOPE: string;

export type DefectType = "ADVISORY" | "DANGEROUS" | "FAIL" | "MAJOR" | "MINOR" | "NON SPECIFIC" | "SYSTEM GENERATED" | "USER ENTERED" | "PRS";

export interface Defect {
  text: string | null;
  type: DefectType | null;
  dangerous?: boolean | null;
}

export interface MotTest {
  registrationAtTimeOfTest?: string | null;
  /** ISO 8601 timestamp, e.g. "2024-02-27T11:42:10.000Z". */
  completedDate: string;
  testResult: "PASSED" | "FAILED";
  /** YYYY-MM-DD; only on passed tests. */
  expiryDate?: string | null;
  /** A string of digits, e.g. "71240". */
  odometerValue?: string | null;
  odometerUnit?: "MI" | "KM" | null;
  odometerResultType: "READ" | "UNREADABLE" | "NO_ODOMETER";
  motTestNumber?: string | null;
  dataSource: "DVSA" | "DVA NI" | "CVS";
  /** CVS (heavy vehicle) tests only. */
  location?: string | null;
  defects?: Defect[] | null;
}

export type OutstandingRecall = "Yes" | "No" | "Unknown" | "Unavailable";

/** A vehicle with at least one test, or a newly registered one (no motTests, has motTestDueDate). */
export interface Vehicle {
  registration: string | null;
  make?: string | null;
  model?: string | null;
  firstUsedDate?: string | null;
  registrationDate?: string | null;
  manufactureDate?: string | null;
  manufactureYear?: string | null;
  fuelType?: string | null;
  primaryColour?: string | null;
  engineSize?: string | null;
  hasOutstandingRecall: OutstandingRecall;
  motTestDueDate?: string | null;
  motTests?: MotTest[];
}

export interface BulkFile {
  filename: string;
  downloadUrl: string;
  fileSize: number;
  fileCreatedOn: string;
}

export interface BulkDownload {
  bulk: BulkFile[];
  delta: BulkFile[];
}

export interface MotHistoryOptions {
  clientId: string;
  clientSecret: string;
  apiKey: string;
  /** Tenant ID from your DVSA credentials email (or pass tokenUrl). */
  tenantId?: string;
  tokenUrl?: string;
  scope?: string;
  baseUrl?: string;
  maxRetries?: number;
  backoffMs?: number;
  timeoutMs?: number;
  fetch?: (input: string, init?: RequestInit) => Promise<Response>;
  sleep?: (ms: number) => Promise<void>;
  now?: () => number;
}

export type MotHistoryErrorKind = "config" | "auth" | "not-found" | "invalid" | "rate-limited" | "upstream";

export declare class MotHistoryError extends Error {
  constructor(message: string, info?: { status?: number; errorCode?: string; kind?: MotHistoryErrorKind });
  status?: number;
  errorCode?: string;
  kind: MotHistoryErrorKind;
}

export declare class MotHistoryClient {
  constructor(options: MotHistoryOptions);
  static fromEnv(env?: Record<string, string | undefined>): MotHistoryClient;
  byRegistration(registration: string): Promise<Vehicle>;
  byVin(vin: string): Promise<Vehicle>;
  bulkDownload(): Promise<BulkDownload>;
  accessToken(force?: boolean): Promise<string>;
}

export interface MileageReading {
  /** YYYY-MM-DD */
  date: string;
  miles: number;
  test: MotTest;
}

export interface MileageAnomaly {
  earlier: MileageReading;
  later: MileageReading;
  drop: number;
}

export declare function normaliseRegistration(value: string): string;
export declare function odometerMiles(test: MotTest): number | null;
export declare function mileageReadings(vehicle: Vehicle): MileageReading[];
export declare function findMileageAnomalies(vehicle: Vehicle, tolerance?: number): MileageAnomaly[];
export declare function motExpiry(vehicle: Vehicle): string | null;
