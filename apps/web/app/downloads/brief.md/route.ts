import { NextResponse } from "next/server";

import { ApiError, apiDownload } from "@/lib/api";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const upstream = await apiDownload("/export/brief.md");
    const body = await upstream.text();
    return new NextResponse(body, {
      headers: {
        "Content-Type": "text/markdown; charset=utf-8",
        "Content-Disposition": 'attachment; filename="discmon-weekly-brief.md"',
        "Cache-Control": "no-store",
      },
    });
  } catch (error) {
    const status = error instanceof ApiError ? error.status : 502;
    return new NextResponse("Brief export is unavailable right now.", {
      status,
      headers: { "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store" },
    });
  }
}
