import { NextResponse } from "next/server";

export async function GET(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const target = new URL(`/imprimir/${id}`, request.url);
  target.search = new URL(request.url).search;
  return NextResponse.redirect(target);
}
