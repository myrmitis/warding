// Universal .app bundles (packaging/build-desktop.sh UNIVERSAL=1) ship one
// complete backend tree per CPU architecture under backend-dist/. Maps a Node
// `process.arch` value to the directory suffix; arches without an entry
// (e.g. "ia32") simply skip the arch-suffixed candidates.
const ARCH_DIR_SUFFIX = { arm64: "arm64", x64: "x64" };

/**
 * Locate the junction backend binary by checking well-known paths in order.
 *
 * Returns the first executable candidate, or bare `"junction"` as a PATH
 * fallback. Dependencies are injected so the function is pure and testable
 * without mocking globals.
 *
 * @param {typeof import("fs")} fs - Node fs module (needs `accessSync`, `constants.X_OK`)
 * @param {typeof import("os")} os - Node os module (needs `homedir()`)
 * @param {typeof import("path")} path - Node path module
 * @param {string|undefined} resourcesPath - `process.resourcesPath` (Electron only)
 * @param {string} dirname - `__dirname` of the calling module
 * @param {string} [arch] - CPU arch selecting the backend tree in universal
 *   bundles (defaults to `process.arch`)
 * @param {boolean} [isWindows] - whether the host is Windows (defaults to
 *   `process.platform === "win32"`). On Windows the backend ships as a real
 *   `junction.exe` console script under `Scripts\` (venv) — Node's `spawn()`
 *   does no PATHEXT resolution for a bare name, so an absolute `.exe` path is
 *   required.
 * @returns {string} Absolute path to the binary, or `"junction"` /
 *   `"junction.exe"` (Windows) as a PATH fallback
 */
function findJunctionBin(
  fs,
  os,
  path,
  resourcesPath,
  dirname,
  arch = process.arch,
  isWindows = process.platform === "win32"
) {
  const home = os.homedir();
  const candidates = [];
  // 0. Universal-bundle layout: arch-suffixed backend trees, selected by the
  //    running shell's arch. Ranked above the unsuffixed layout so a universal
  //    bundle never falls back to a wrong-arch tree; plain per-arch bundles
  //    don't ship these dirs so the probes miss (ENOENT) and fall through.
  const suffix = ARCH_DIR_SUFFIX[arch];
  if (suffix) {
    const archBackend = `junction-backend-${suffix}`;
    candidates.push(
      path.join(resourcesPath || "", "backend-dist", archBackend, "bin", "junction"),
      path.resolve(dirname, "backend-dist", archBackend, "bin", "junction")
    );
  }
  // 1. Windows SOURCE CHECKOUT: a pip/venv install exposes `junction.exe`
  //    under `Scripts\` (not the POSIX `bin/junction` launcher). Probed before
  //    the bundled candidates so a developer running from a checkout gets
  //    their own venv, and as an absolute `.exe` that `spawn()` can launch
  //    without a shell. On POSIX these are skipped entirely so mac/Linux
  //    behavior is unchanged.
  //
  //    Only the checkout venvs are ranked here. The BUNDLE's own
  //    Scripts\junction.exe is ranked further down, below the .cmd shim --
  //    see the note there.
  if (isWindows) {
    candidates.push(
      // Source checkout: repo-root `.venv` — electron/ is <repo>/website/electron,
      // so the venv is two levels up; one level up covers a <repo>/website venv.
      path.resolve(dirname, "..", "..", ".venv", "Scripts", "junction.exe"),
      path.resolve(dirname, "..", ".venv", "Scripts", "junction.exe")
    );
  }
  candidates.push(
    // 2. Windows bundled layout (packaging/build-desktop.sh
    //    build_backend_windows): the PBS interpreter ships python.exe at
    //    the tree root with a bin\junction.cmd launcher shim. Probed on
    //    every platform (costs one ENOENT elsewhere) so this function
    //    stays platform-agnostic and testable; only a Windows bundle
    //    actually contains the .cmd. Keep in sync with
    //    build-desktop.sh's bin/junction.cmd.
    //
    //    This MUST outrank backend-dist/.../Scripts/junction.exe below.
    //    `pip install` also drops a console-script .exe in the bundle's
    //    Scripts\ dir, but distlib embeds the ABSOLUTE interpreter path of
    //    the machine that built it, so inside a shipped bundle that .exe
    //    points at a build-agent path (D:\a\Junction\...) that does not
    //    exist on the user's machine. The .cmd shim resolves the
    //    interpreter via %~dp0 and is the only relocatable launcher of the
    //    two. Ranking them the other way round both broke the build-time
    //    resolver gate and, had the gate not caught it, would have shipped
    //    an app whose backend could never start.
    path.join(resourcesPath || "", "backend-dist", "junction-backend", "bin", "junction.cmd"),
    path.resolve(dirname, "backend-dist", "junction-backend", "bin", "junction.cmd"),
    // 3. Bundled POSIX layout (packaging/build-desktop.sh): a
    //    python-build-standalone interpreter copied into backend-dist with a
    //    `bin/junction` launcher wrapper (exec python3.12 -s -m junction).
    //    This is what a freshly-built .app actually ships. Keep this in sync
    //    with build-desktop.sh's BACKEND_OUT/bin/junction path.
    path.join(resourcesPath || "", "backend-dist", "junction-backend", "bin", "junction"),
    path.resolve(dirname, "backend-dist", "junction-backend", "bin", "junction"),
    path.resolve(dirname, "..", "bin", "junction")
  );
  if (isWindows) {
    // 4. The bundle's pip console-script .exe. Ranked BELOW the .cmd shim
    //    (distlib bakes the building machine's absolute interpreter path into
    //    it, so in a shipped bundle it points at a path that does not exist)
    //    but still ABOVE the user-level install paths below: a bundled app
    //    must prefer its own backend over whatever happens to be installed on
    //    the machine. It is correct for a bundle built where it runs (a local
    //    `make desktop`), which is why it is probed at all.
    candidates.push(
      path.join(resourcesPath || "", "backend-dist", "junction-backend", "Scripts", "junction.exe"),
      path.resolve(dirname, "backend-dist", "junction-backend", "Scripts", "junction.exe")
    );
  }
  // 5. Well-known install paths (installer symlink and venv). Last,
  //    so a packaged app never prefers a stray user-level install over the
  //    backend it shipped with.
  candidates.push(
    path.join(home, ".local", "bin", "junction"),
    path.join(home, ".junction-app", ".venv", "bin", "junction")
  );
  if (isWindows) {
    // Windows equivalents of the user-level paths above (one-liner installer
    // venv and local pip Scripts dirs).
    candidates.push(
      path.join(home, ".junction-app", ".venv", "Scripts", "junction.exe"),
      path.join(home, ".local", "bin", "junction.exe")
    );
  }
  for (const bin of candidates) {
    try {
      fs.accessSync(bin, fs.constants.X_OK);
      return bin;
    } catch (e) {
      if (e.code !== "ENOENT") console.warn(`junction candidate ${bin}: ${e.code}`);
    }
  }
  return isWindows ? "junction.exe" : "junction"; // fall back to PATH
}

module.exports = { findJunctionBin };
