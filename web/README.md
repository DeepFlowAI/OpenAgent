# OpenAgent Frontend

Next.js frontend for the OpenAgent multi-tenant management platform.

## Tech Stack

- **Framework**: Next.js 15 (App Router) + React 19
- **Styling**: TailwindCSS 4
- **State**: React Query (server) + Zustand (global)
- **HTTP**: ky
- **Validation**: Zod

## Quick Start

```bash
# 1. Install dependencies
npm install

# 2. Run dev server
npm run dev
```

## Environment

- `APP_ENV=dev` (default) → loads `.env.dev`
- `APP_ENV=production` → loads `.env.production`

```bash
APP_ENV=production npm run build
```

## Project Structure

```
web/
├── app/                    # Pages & layouts
│   ├── components/         # UI components
│   ├── (auth)/             # Auth pages
│   └── (main)/             # Authenticated pages
├── context/                # Zustand stores & providers
├── service/                # API service hooks
├── models/                 # Type definitions
├── utils/                  # Utilities
└── styles/                 # Global styles
```
