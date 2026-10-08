import type {
  AnalysisJobResponse,
  AnalysisResponse,
  GitHubSession,
} from "./types";

const DIRECT_API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api";
const API_URL =
  process.env.NEXT_PUBLIC_API_PROXY === "true" ? "/api" : DIRECT_API_URL;

export const apiDocsUrl = new URL("/docs", DIRECT_API_URL).toString();
export const githubLoginUrl = `${API_URL}/auth/github`;

async function readJson<T>(response: Response, context: string): Promise<T> {
  const body = await response.text();
  if (!body.trim()) {
    throw new Error(`${context}: API returned an empty response (HTTP ${response.status}).`);
  }

  try {
    return JSON.parse(body) as T;
  } catch {
    throw new Error(`${context}: API returned invalid JSON (HTTP ${response.status}).`);
  }
}

export async function getGitHubSession(): Promise<GitHubSession> {
  const response = await fetch(`${API_URL}/auth/me`, { credentials: "include" });
  if (!response.ok) throw new Error("Could not read GitHub sign-in status.");
  return readJson<GitHubSession>(response, "Could not read GitHub sign-in status");
}

export async function logoutGitHub(): Promise<void> {
  const response = await fetch(`${API_URL}/auth/logout`, {
    method: "POST",
    credentials: "include",
  });
  if (!response.ok) throw new Error("Could not sign out of GitHub.");
}

async function detailFromResponse(response: Response): Promise<string> {
  const body = await response.text();
  if (!body.trim()) {
    return `API returned an empty error response (HTTP ${response.status}).`;
  }

  try {
    const parsed: unknown = JSON.parse(body);
    return typeof parsed === "object" &&
      parsed !== null &&
      "detail" in parsed &&
      typeof parsed.detail === "string"
      ? parsed.detail
      : `Analysis failed (HTTP ${response.status}). Check the API and repository URL.`;
  } catch {
    return `API returned a non-JSON error response (HTTP ${response.status}).`;
  }
}

export async function analyzeLocalPath(path: string): Promise<AnalysisResponse> {
  const response = await fetch(`${API_URL}/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path }),
    credentials: "include",
  });

  if (!response.ok) {
    throw new Error(await detailFromResponse(response));
  }

  return readJson<AnalysisResponse>(response, "Analysis failed");
}

export async function startGitHubAnalysis(
  url: string,
): Promise<AnalysisJobResponse> {
  const response = await fetch(`${API_URL}/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source: { type: "github", url } }),
    credentials: "include",
  });

  if (!response.ok) {
    throw new Error(await detailFromResponse(response));
  }

  return readJson<AnalysisJobResponse>(response, "Could not start analysis");
}

export async function getAnalysisJob(
  analysisId: string,
): Promise<AnalysisJobResponse> {
  const response = await fetch(
    `${API_URL}/analyses/${encodeURIComponent(analysisId)}`,
    { credentials: "include" },
  );
  if (!response.ok) throw new Error(await detailFromResponse(response));
  return readJson<AnalysisJobResponse>(response, "Could not read analysis status");
}
