import text from "../../../NOTICE?raw";

export function GET() {
  return new Response(text, { headers: { "Content-Type": "text/plain; charset=utf-8" } });
}
