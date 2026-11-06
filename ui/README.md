This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Data

This dashboard reads static JSON from `public/data/`:
- `public/data/report.json` — `build_report()` output.
- `public/data/runs/*.json` — a bounded subset of `RunRecord.to_json()` files, plus `public/data/runs/index.json` listing their ids (used by `generateStaticParams`).

Run `uv run ms snapshot` from the repo root to (re)populate these from `results/report.json` and `results/runs/*.json`. Until the real evaluation matrix finishes, `public/data/` ships with a small hand-written sample dataset so the UI builds and is screenshotable today — `ms snapshot` overwrites it with real data once available.

## Build (static export)

```bash
node scripts/check-data.mjs   # verify public/data/ fixtures are present/shaped correctly
npm run lint
npm run build                 # -> ui/out/ (output: "export" in next.config.ts)
```

## Deploy

Deliberately **not done by the agent**. Once `ui/out/` is built, a human runs:

```bash
vercel login
vercel deploy ui/out --prod
```

(or the Vercel CLI token flow from the `vercel-cli-deploy` skill). Record the resulting URL here once deployed.

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.
