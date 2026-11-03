// Cloudflare Worker: fires one workflow_dispatch of watch.yml per cron tick.
// No inputs, so watch.py runs one pass of the normal watch[] list.
// Never logs GITHUB_TOKEN. Throwing marks the invocation as failed in Cloudflare.

const HINTS = {
  401: "token expired, revoked, or wrong",
  403: "token lacks Actions write, or the workflow is disabled",
  404: "wrong owner/repo/workflow, or the token can't see this repo",
  422: "bad ref, or watch.yml has no workflow_dispatch trigger on that ref",
};

export async function dispatch(env) {
  if (!env.GITHUB_TOKEN) {
    throw new Error("GITHUB_TOKEN secret unset, run: npx wrangler@4 secret put GITHUB_TOKEN");
  }
  const url = `https://api.github.com/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}/actions/workflows/${env.GITHUB_WORKFLOW}/dispatches`;
  const res = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.GITHUB_TOKEN}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2026-03-10",
      "User-Agent": "class-bot-cron-worker",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ ref: env.GITHUB_REF }),
    signal: AbortSignal.timeout(20000),
  });
  if (!res.ok) {
    const body = (await res.text()).slice(0, 300);
    const hint = HINTS[res.status] || "GitHub error, next tick retries";
    throw new Error(`dispatch failed: HTTP ${res.status} (${hint}): ${body}`);
  }
  console.log(`dispatch ok: HTTP ${res.status}`);
}

export default {
  async scheduled(controller, env) {
    await dispatch(env);
  },
};
