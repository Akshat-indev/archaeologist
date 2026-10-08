import type {
  AnalysisJobResponse,
  AnalysisResponse,
  GitHubSession,
} from "./types";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api";

export const githubLoginUrl = `${API_URL}/auth/github`;

export async function getGitHubSession(): Promise<GitHubSession> {
  const response = await fetch(`${API_URL}/auth/me`, { credentials: "include" });
  if (!response.ok) throw new Error("Could not read GitHub sign-in status.");
  return (await response.json()) as GitHubSession;
}

export async function logoutGitHub(): Promise<void> {
  const response = await fetch(`${API_URL}/auth/logout`, {
    method: "POST",
    credentials: "include",
  });
  if (!response.ok) throw new Error("Could not sign out of GitHub.");
}

async function detailFromResponse(response: Response): Promise<string> {
  const body: unknown = await response.json();
  return typeof body === "object" &&
    body !== null &&
    "detail" in body &&
    typeof body.detail === "string"
    ? body.detail
    : "Analysis failed. Check the API and repository URL.";
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

  return (await response.json()) as AnalysisResponse;
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

  return (await response.json()) as AnalysisJobResponse;
}

export async function getAnalysisJob(
  analysisId: string,
): Promise<AnalysisJobResponse> {
  const response = await fetch(
    `${API_URL}/analyses/${encodeURIComponent(analysisId)}`,
    { credentials: "include" },
  );
  if (!response.ok) throw new Error(await detailFromResponse(response));
  return (await response.json()) as AnalysisJobResponse;
}
