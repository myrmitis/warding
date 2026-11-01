// Website copy revised by Myrmitis on 2026-10-08; inherited legal attribution preserved in NOTICE.
// Public release summary revised by Myrmitis, 2026-10-08; original release notes remain in the preserved source tree.
export function GET() {
  return new Response("No tagged Warding release yet. Public source is available on GitHub. Original release notes remain in the source tree. See /changelog/ for the public release summary.\n", { headers: { "Content-Type": "text/plain; charset=utf-8" } });
}
