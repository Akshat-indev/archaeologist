"use client";

import { startTransition, useEffect, useState, type FormEvent } from "react";
import Link from "next/link";

import { AnalysisDashboard } from "@/components/analysis/AnalysisDashboard";
import {
  analyzeLocalPath,
  getAnalysisJob,
  getGitHubSession,
  githubLoginUrl,
  logoutGitHub,
  startGitHubAnalysis,
} from "@/lib/api";
import type {
  AnalysisJobResponse,
  AnalysisResponse,
  GitHubUser,
} from "@/lib/types";

const PROGRESS_LABELS: Record<string, string> = {
  created: "Starting analysis",
  cloning: "Cloning repository",
  scanning: "Scanning repository",
  parsing: "Parsing source files",
  analyzing: "Analyzing behavior",
  building_flows: "Building application flows",
};

export default function Home() {
  const [repositoryUrl, setRepositoryUrl] = useState("");
  const [repositoryPath, setRepositoryPath] = useState(
    "../../engine/tests/fixtures/login_app",
  );
  const [sourceMode, setSourceMode] = useState<"github" | "local">("local");

  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [job, setJob] = useState<AnalysisJobResponse | null>(null);

  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const [githubUser, setGithubUser] = useState<GitHubUser | null>(null);
  const [authConfigured, setAuthConfigured] = useState(false);
  const [authLoading, setAuthLoading] = useState(true);
  const [authNotice, setAuthNotice] = useState("");

  useEffect(() => {
    let active = true;

    const query = new URLSearchParams(window.location.search);
    const authResult = query.get("auth");

    if (authResult) {
      startTransition(() => {
        setAuthNotice(
          authResult === "connected"
            ? "GitHub account connected."
            : authResult === "cancelled"
              ? "GitHub sign-in was cancelled."
              : authResult === "invalid_state"
                ? "GitHub sign-in expired. Please try again."
                : "GitHub sign-in failed. Please try again.",
        );
      });

      query.delete("auth");

      const queryString = query.toString();

      window.history.replaceState(
        null,
        "",
        `${window.location.pathname}${
          queryString ? `?${queryString}` : ""
        }${window.location.hash}`,
      );
    }

    void getGitHubSession()
      .then((session) => {
        if (!active) return;

        setGithubUser(session.user);
        setAuthConfigured(session.configured);
      })
      .catch(() => {
        if (active) {
          setAuthConfigured(false);
        }
      })
      .finally(() => {
        if (active) {
          setAuthLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, []);

  async function handleSignOut() {
    try {
      await logoutGitHub();

      setGithubUser(null);
      setAnalysis(null);
      setJob(null);
      setAuthNotice("Signed out of GitHub.");
    } catch (authError) {
      setAuthNotice(
        authError instanceof Error
          ? authError.message
          : "Could not sign out.",
      );
    }
  }

  async function handleAnalyze(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!githubUser) {
      setError("Sign in with GitHub before analyzing a repository.");
      return;
    }

    setError("");
    setLoading(true);
    setJob(null);

    try {
      if (sourceMode === "local") {
        setAnalysis(await analyzeLocalPath(repositoryPath.trim()));
        return;
      }

      let currentJob = await startGitHubAnalysis(repositoryUrl.trim());

      setJob(currentJob);

      while (
        currentJob.status !== "complete" &&
        currentJob.status !== "failed"
      ) {
        await new Promise((resolve) =>
          window.setTimeout(resolve, 700),
        );

        currentJob = await getAnalysisJob(currentJob.analysis_id);
        setJob(currentJob);
      }

      if (currentJob.status === "failed") {
        throw new Error(
          currentJob.error ?? "Repository analysis failed.",
        );
      }

      if (!currentJob.result) {
        throw new Error(
          "Analysis completed without a result.",
        );
      }

      setAnalysis(currentJob.result);
    } catch (analysisError) {
      setError(
        analysisError instanceof Error
          ? analysisError.message
          : "Analysis failed. Check the API and repository URL.",
      );
    } finally {
      setLoading(false);
    }
  }

  if (analysis && githubUser) {
    return (
      <AnalysisDashboard
        analysis={analysis}
        githubUser={githubUser}
        onSignOut={handleSignOut}
        onNewAnalysis={() => {
          setAnalysis(null);
          setJob(null);
          setError("");
        }}
      />
    );
  }

  const progress = job?.progress;

  const hasProgressCounts =
    !!progress &&
    (progress.files_discovered > 0 ||
      progress.files_analyzed > 0 ||
      progress.files_skipped > 0);

  const currentValue =
    sourceMode === "local"
      ? repositoryPath.trim()
      : repositoryUrl.trim();

  const canSubmit =
    !!githubUser &&
    !loading &&
    currentValue !== "";

  return (
    <main className="landing">
      <header className="landing-header">
        <Link
          className="brand"
          href="/"
          aria-label="Archaeologist home"
        >
          <span className="brand-mark" aria-hidden="true">
            <span />
            <span />
            <span />
            <span />
          </span>

          <span>Archaeologist</span>
        </Link>

        <div className="landing-header-actions">
          {githubUser ? (
            <div className="github-account">
              {githubUser.avatar_url && (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  alt=""
                  height="26"
                  src={githubUser.avatar_url}
                  width="26"
                />
              )}

              <span>{githubUser.login}</span>

              <button
                className="text-button"
                onClick={() => void handleSignOut()}
                type="button"
              >
                Sign out
              </button>
            </div>
          ) : authLoading ? null : authConfigured ? (
            <a
              className="button button-quiet"
              href={githubLoginUrl}
            >
              Sign in with GitHub
            </a>
          ) : (
            <button
              className="button button-quiet"
              disabled
              title="Configure the GitHub OAuth app in the API environment."
              type="button"
            >
              Sign in unavailable
            </button>
          )}

          <a
            className="header-link"
            href="http://localhost:8000/docs"
            target="_blank"
            rel="noreferrer"
          >
            API docs
          </a>
        </div>
      </header>

      <section className="landing-content">
        <div className="landing-copy">
          <div className="eyebrow">
            CODEBASE INTELLIGENCE
          </div>

          <h1>
            Understand what your <span className="red-head">code does</span> when a user clicks.
          </h1>

          <p>
            Archaeologist reads your repository and traces
            application behavior from frontend events to API
            requests and backend handlers.
          </p>

          <ol className="trace-sample">
            <li className="trace-step">
              <span>Click handler</span>
              <code>LoginForm.handleSubmit</code>
            </li>

            <li className="trace-step http">
              <span>HTTP request</span>
              <code>POST /api/login</code>
            </li>

            <li className="trace-step route">
              <span>Backend route</span>
              <code>login_user</code>
            </li>
          </ol>
        </div>

        <form
          className="analyze-panel"
          onSubmit={handleAnalyze}
        >
          <div className="panel-heading">
            <div>
              <span className="panel-kicker">
                START EXPLORING
              </span>

              <h2 className="panel-title">
                Analyze a repository
              </h2>
            </div>

            <span className="panel-status">
              {githubUser ? "Ready" : "GitHub required"}
            </span>
          </div>

          {authNotice && (
            <p className="auth-notice" role="status">
              {authNotice}
            </p>
          )}

          {!githubUser && !authLoading && (
            <p className="auth-notice" role="status">
              {authConfigured
                ? "Connect GitHub to analyze repositories."
                : "GitHub sign-in is not configured on the API server."}
            </p>
          )}

          <div
            className="analysis-modes"
            aria-label="Analysis source"
            role="group"
          >
            <button
              aria-pressed={sourceMode === "local"}
              className={
                sourceMode === "local"
                  ? "analysis-mode active"
                  : "analysis-mode"
              }
              disabled={!githubUser}
              onClick={() => setSourceMode("local")}
              type="button"
            >
              Local
            </button>

            <button
              aria-pressed={sourceMode === "github"}
              className={
                sourceMode === "github"
                  ? "analysis-mode active"
                  : "analysis-mode"
              }
              disabled={!githubUser}
              onClick={() => setSourceMode("github")}
              type="button"
            >
              GitHub
            </button>
          </div>

          <label
            className="path-label"
            htmlFor={
              sourceMode === "local"
                ? "repository-path"
                : "repository-url"
            }
          >
            {sourceMode === "local"
              ? "Repository path"
              : "Repository URL"}
          </label>

          <div className="path-input-wrap">
            {sourceMode === "local" ? (
              <input
                autoComplete="off"
                disabled={!githubUser}
                id="repository-path"
                onChange={(event) =>
                  setRepositoryPath(event.target.value)
                }
                placeholder="/path/to/repository"
                required
                spellCheck={false}
                value={repositoryPath}
              />
            ) : (
              <input
                autoComplete="off"
                disabled={!githubUser}
                id="repository-url"
                onChange={(event) =>
                  setRepositoryUrl(event.target.value)
                }
                placeholder="https://github.com/owner/repository"
                required
                spellCheck={false}
                value={repositoryUrl}
              />
            )}
          </div>

          <p className="input-help">
            {sourceMode === "local"
              ? "Reads JavaScript and TypeScript source files from the API server."
              : "Analyze a public GitHub repository without granting repository permissions."}
          </p>

          {loading && job && (
            <div
              className="analysis-progress"
              role="status"
            >
              <div className="analysis-progress-heading">
                <span className="spinner" />

                <span>
                  {PROGRESS_LABELS[job.status] ?? "Working"}
                </span>
              </div>

              <span>
                {hasProgressCounts && progress
                  ? `${progress.files_analyzed} of ${progress.files_discovered} supported files parsed, ${progress.files_skipped} skipped`
                  : "Collecting repository inventory"}
              </span>
            </div>
          )}

          {error && (
            <div
              className="error-message"
              role="alert"
            >
              <p>{error}</p>
            </div>
          )}

          {!githubUser &&
          !authLoading &&
          authConfigured ? (
            <a
              className="button button-primary analyze-button"
              href={githubLoginUrl}
            >
              Continue with GitHub
            </a>
          ) : (
            <button
              className="button button-primary analyze-button"
              disabled={!canSubmit}
              type="submit"
            >
              {loading ? (
                <>
                  <span className="spinner" />
                  Analyzing repository
                </>
              ) : (
                <>
                  Analyze repository
                  <span aria-hidden="true">→</span>
                </>
              )}
            </button>
          )}

        </form>
      </section>
    </main>
  );
}