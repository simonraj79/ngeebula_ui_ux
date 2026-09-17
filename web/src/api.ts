export type ScenarioId = "A" | "B" | "C";

export interface DatasetSummary {
  dataset_id: string;
  source_name: string;
  source_commit?: string;
  source_attribution?: string;
  imported_at: string;
  horizon_start: string;
  horizon_end: string;
  contracts: number;
  activities: number;
  locations: number;
  access_weeks: number;
  lines: Array<"Alpha" | "Beta">;
  network_stations: Array<{
    station_id: string;
    line_code: "ALP" | "BET";
    seq: number;
    is_interchange: boolean;
  }>;
  warnings: string[];
  location_options: Array<{ id: string; line: string; bound: string; capacity: number }>;
  week_options: Array<{ value: string; start: string; end: string }>;
}

export interface ScenarioResult {
  scenario: ScenarioId;
  complete: boolean;
  feasible: boolean;
  hard_violations: Array<{ rule: string; severity: "hard"; detail: string }>;
  soft_scores: {
    objective_score?: number;
    overrun_days_total: number;
    contracts_overrunning: number;
    excess_access_nights_total: number;
    eclo_nights_total: number;
    priority_weighted_score: number;
  };
  detail: {
    nights_scheduled: number;
    eclo_nights: number;
    capacity_hotspots: unknown[];
  };
}

export interface ScheduleRow {
  activity_id: string;
  contract_number: string;
  line: "Alpha" | "Beta";
  activity_type: "PM" | "PC" | "C" | string;
  access_type: string;
  contract_priority: 1 | 2 | 3;
  week: string;
  start_location_id: string;
  end_location_id: string;
  access_night: number;
  eclo: boolean;
  co_share_group?: string | null;
}

export interface PlanBundle {
  run_id?: string;
  dataset: DatasetSummary;
  result: ScenarioResult;
  schedule: ScheduleRow[];
  generated_at: string;
  explanations: Array<{ code: string; message: string }>;
  changes?: {
    baseline_run_id?: string | null;
    count: number;
    moved_activities: Array<{ activity_id: string; before: unknown[]; after: unknown[] }>;
    note?: string;
  };
}

interface DatasetResponse {
  dataset_id: string;
  created_at?: string;
  label?: string;
  source?:
    | string
    | { name?: string; kind?: string; attribution?: string; commit?: string };
  audit?: {
    valid?: boolean;
    issues?: Array<string | { detail?: string; message?: string }>;
    counts?: Record<string, number>;
  };
  contracts?: unknown[];
  activities?: unknown[];
  locations?: unknown[];
  horizon_start?: string;
  horizon_weeks?: number;
  weeks?: Array<
    string | number | { week?: string | number; start?: string; end?: string }
  >;
  lines?: Array<string | { line_code?: string; line_name?: string }>;
  network?: {
    lines?: Array<string | { line_code?: string; line_name?: string }>;
    stations?: Array<{
      station_id: string;
      line_code: "ALP" | "BET";
      seq: number;
      is_interchange: boolean;
    }>;
  };
}

interface RunResponse {
  run_id: string;
  status: "queued" | "running" | "completed" | "failed";
  result?: unknown;
  error?: string;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message);
  }
}

const BASE =
  (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "") ||
  "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, init);
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      message = String(body.detail ?? body.message ?? message);
    } catch {
      /* non-JSON */
    }
    throw new ApiError(message, response.status);
  }
  return response.json() as Promise<T>;
}

function normalizeDataset(raw: DatasetResponse): DatasetSummary {
  const counts = raw.audit?.counts ?? {};
  const weeks = raw.weeks ?? [];
  const weekLabel = (value: (typeof weeks)[number] | undefined, end = false) =>
    typeof value === "object" && value !== null
      ? String((end ? value.end : value.start) ?? value.week ?? "Not reported")
      : String(value ?? "Not reported");
  const lineValues = raw.network?.lines ?? raw.lines ?? [];
  return {
    dataset_id: raw.dataset_id,
    source_name:
      typeof raw.source === "string"
        ? raw.source
        : (raw.source?.name ??
          raw.source?.kind ??
          raw.label ??
          "Imported dataset"),
    source_commit:
      typeof raw.source === "object" ? raw.source?.commit : undefined,
    source_attribution:
      typeof raw.source === "object" ? raw.source?.attribution : undefined,
    imported_at: raw.created_at ?? "Not reported",
    horizon_start: raw.horizon_start ?? weekLabel(weeks[0]),
    horizon_end: weekLabel(weeks[weeks.length - 1], true),
    contracts: counts.contracts ?? raw.contracts?.length ?? 0,
    activities: counts.activities ?? raw.activities?.length ?? 0,
    locations: counts.locations ?? raw.locations?.length ?? 0,
    access_weeks: counts.weeks ?? raw.horizon_weeks ?? weeks.length,
    lines: lineValues
      .map((x) =>
        typeof x === "string" ? x : (x.line_name ?? x.line_code ?? ""),
      )
      .map((x) =>
        x === "ALP" || x === "Line Alpha"
          ? "Alpha"
          : x === "BET" || x === "Line Beta"
            ? "Beta"
            : x,
      )
      .filter((x): x is "Alpha" | "Beta" => x === "Alpha" || x === "Beta"),
    warnings: (raw.audit?.issues ?? []).map((issue) =>
      typeof issue === "string"
        ? issue
        : (issue.message ?? issue.detail ?? "Dataset audit issue"),
    ),
    network_stations: raw.network?.stations ?? [],
    location_options: (raw.locations ?? []).map((item) => {
      const row = item as Record<string, unknown>;
      return { id: String(row.location_id ?? ""), line: String(row.line_code ?? ""), bound: String(row.bound ?? ""), capacity: Number(row.supply_capacity ?? 0) };
    }),
    week_options: weeks.map((item) => {
      const row = typeof item === "object" && item !== null ? item : { week: item };
      return { value: String(row.week ?? ""), start: String(row.start ?? ""), end: String(row.end ?? "") };
    }),
  };
}

function normalizeBundle(
  raw: unknown,
  scenario: ScenarioId,
  dataset: DatasetSummary,
  runId?: string,
): PlanBundle {
  const body = (raw && typeof raw === "object" ? raw : {}) as Record<
    string,
    unknown
  >;
  const validation = (body.validation ??
    body.report ??
    body.result ??
    body) as Record<string, unknown>;
  const score = (validation.soft_scores ?? {}) as Record<string, unknown>;
  const detail = (validation.detail ?? {}) as Record<string, unknown>;
  const hard = Array.isArray(validation.hard_violations)
    ? validation.hard_violations
    : [];
  const sourceSchedule = Array.isArray(body.schedule)
    ? (body.schedule as Array<Record<string, unknown>>)
    : [];
  const schedule = sourceSchedule.map((row) => ({
    activity_id: String(row.activity_id ?? ""),
    contract_number: String(row.contract_number ?? row.project_id ?? ""),
    line: (row.line === "Beta" || row.line_code === "BET"
      ? "Beta"
      : "Alpha") as "Alpha" | "Beta",
    activity_type: String(row.activity_type ?? ""),
    access_type: String(row.access_type ?? ""),
    contract_priority: Number(row.contract_priority ?? 3) as 1 | 2 | 3,
    week: String(row.week ?? ""),
    start_location_id: String(row.start_location_id ?? row.location_id ?? ""),
    end_location_id: String(row.end_location_id ?? row.location_id ?? ""),
    access_night: Number(row.access_night ?? 0),
    eclo: row.eclo === true || row.eclo === 1,
    co_share_group:
      row.co_share_group == null ? null : String(row.co_share_group),
  }));
  return {
    run_id: runId,
    dataset,
    generated_at: String(body.generated_at ?? new Date().toISOString()),
    schedule,
    explanations: Array.isArray(body.explanations)
      ? (body.explanations as Array<Record<string, unknown>>).map((x) => ({ code: String(x.code ?? ""), message: String(x.message ?? "") }))
      : [],
    changes: body.changes && typeof body.changes === "object"
      ? body.changes as PlanBundle["changes"]
      : undefined,
    result: {
      scenario,
      complete: validation.complete === true,
      feasible: body.feasible === true && validation.complete === true,
      hard_violations: hard as ScenarioResult["hard_violations"],
      soft_scores: {
        objective_score:
          typeof score.objective_score === "number"
            ? score.objective_score
            : undefined,
        overrun_days_total: Number(score.overrun_days_total ?? 0),
        contracts_overrunning: Number(score.contracts_overrunning ?? 0),
        excess_access_nights_total: Number(
          score.excess_access_nights_total ?? 0,
        ),
        eclo_nights_total: Number(score.eclo_nights_total ?? 0),
        priority_weighted_score: Number(score.priority_weighted_score ?? 0),
      },
      detail: {
        nights_scheduled: Number(detail.nights_scheduled ?? schedule.length),
        eclo_nights: Number(detail.eclo_nights ?? 0),
        capacity_hotspots: Array.isArray(detail.capacity_hotspots)
          ? detail.capacity_hotspots
          : [],
      },
    },
  };
}

const activeDatasetKey = "ngeebula:ps1:active-dataset";
const activeDatasetId = () => localStorage.getItem(activeDatasetKey) || "default";
const cacheKey = (datasetId: string, scenario: ScenarioId) =>
  `ngeebula:ps1:plan:${datasetId}:${scenario}`;

export const ps1Api = {
  getDataset: async () => {
    const id = activeDatasetId();
    try {
      return normalizeDataset(await request<DatasetResponse>(`/ps1/dataset?dataset_id=${encodeURIComponent(id)}`));
    } catch (error) {
      if (id !== "default" && error instanceof ApiError && error.status === 404) {
        throw new ApiError("The imported dataset expired after the server restarted. Import the eight CSV files again, or restore the supplied dataset.", 404);
      }
      throw error;
    }
  },
  useSuppliedDataset: () => {
    localStorage.setItem(activeDatasetKey, "default");
  },
  getPlan: async (scenario: ScenarioId) => {
    const saved = sessionStorage.getItem(cacheKey(activeDatasetId(), scenario));
    if (!saved)
      throw new ApiError(
        `No completed Scenario ${scenario} run is available in this browser.`,
        404,
      );
    return JSON.parse(saved) as PlanBundle;
  },
  generatePlan: async (
    scenario: ScenarioId,
    options?: {
      baseline_run_id?: string;
      disruptions?: Array<{
        location_id: string;
        week: string;
        capacity: number;
      }>;
    },
  ) => {
    const dataset = normalizeDataset(
      await request<DatasetResponse>(`/ps1/dataset?dataset_id=${encodeURIComponent(activeDatasetId())}`),
    );
    const queued = await request<RunResponse>("/ps1/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        dataset_id: dataset.dataset_id,
        scenario,
        time_limit_seconds: 20,
        ...options,
      }),
    });
    for (let attempt = 0; attempt < 120; attempt += 1) {
      const run =
        attempt === 0
          ? queued
          : await request<RunResponse>(`/ps1/runs/${queued.run_id}`);
      if (run.status === "failed")
        throw new ApiError(run.error || "The planning run failed.");
      if (run.status === "completed") {
        const bundle = normalizeBundle(
          run.result,
          scenario,
          dataset,
          queued.run_id,
        );
        sessionStorage.setItem(cacheKey(dataset.dataset_id, scenario), JSON.stringify(bundle));
        return bundle;
      }
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
    throw new ApiError("The planning run did not finish within two minutes.");
  },
  importDataset: async (files: File[]) => {
    let response: DatasetResponse;
    const zip = files.length === 1 && files[0].name.toLowerCase().endsWith(".zip") ? files[0] : null;
    if (zip) {
      response = await request<DatasetResponse>("/ps1/datasets/import", {
        method: "POST",
        headers: {
          "Content-Type": "application/zip",
          "X-Dataset-Name": zip.name,
        },
        body: zip,
      });
    } else {
      const csvFiles = Object.fromEntries(await Promise.all(files.map(async (file) => [file.name, await file.text()])));
      response = await request<DatasetResponse>("/ps1/datasets/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: files.length === 8 ? "Eight CSV planning instance" : files.map((f) => f.name).join(", "),
          files: csvFiles,
        }),
      });
    }
    localStorage.setItem(activeDatasetKey, response.dataset_id);
    return normalizeDataset(response);
  },
  downloadRun: async (runId: string) => {
    const response = await fetch(
      `${BASE}/ps1/runs/${encodeURIComponent(runId)}/download`,
    );
    if (!response.ok)
      throw new ApiError(
        `Download failed (${response.status})`,
        response.status,
      );
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `ngeebula-${runId}.zip`;
    anchor.click();
    URL.revokeObjectURL(url);
  },
  downloadValidation: async (runId: string) => {
    const response = await fetch(
      `${BASE}/ps1/runs/${encodeURIComponent(runId)}/validation.json`,
    );
    if (!response.ok)
      throw new ApiError(
        `Validation download failed (${response.status})`,
        response.status,
      );
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `ngeebula-${runId}-local-validation.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  },
  getJobs: () => request<Array<Record<string, unknown>>>("/jobs/"),
  getCatalog: () => request<Record<string, unknown>>("/catalog/"),
  getAudit: () => request<Array<Record<string, unknown>>>("/audit-logs/"),
  createJob: (payload: Record<string, unknown>) =>
    request<Record<string, unknown>>("/jobs/parse-and-create", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  proposeMaintenance: () =>
    request<Record<string, unknown>>("/schedule/propose", { method: "POST" }),
  approveJob: (jobId: number, payload: Record<string, unknown>) =>
    request<Record<string, unknown>>(`/approval/${jobId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  updateJobStatus: (jobId: number, payload: Record<string, unknown>) =>
    request<Record<string, unknown>>(`/checklist/${jobId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
};
