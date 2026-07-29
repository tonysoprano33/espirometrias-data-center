import { NextResponse } from "next/server";

export async function GET(request: Request) {
  const target = new URL("/imprimir-dia", request.url);
  target.search = new URL(request.url).search;
  return NextResponse.redirect(target);
}
