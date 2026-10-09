const { describe, it } = require("node:test");
const assert = require("node:assert/strict");
const path = require("path");
const fs = require("fs");
const { findWardingBin } = require("../find-bin");

const HOME = "/mock/home";
const RESOURCES = "/mock/resources";
const DIRNAME = "/mock/electron";

const fakeOs = { homedir: () => HOME };

const only = (target) => ({
  accessSync: (p) => { if (p !== target) throw new Error("ENOENT"); },
  constants: { X_OK: fs.constants.X_OK },
});

const none = {
  accessSync: () => { throw new Error("ENOENT"); },
  constants: { X_OK: fs.constants.X_OK },
};

describe("findWardingBin", () => {
  it("returns the bundled backend launcher (backend-dist/.../bin/warding) when it exists", () => {
    const venvLayout = path.join(RESOURCES, "backend-dist", "warding-backend", "bin", "warding");
    const fakeFs = only(venvLayout);
    const result = findWardingBin(fakeFs, fakeOs, path, RESOURCES, DIRNAME);
    assert.equal(result, venvLayout);
  });

  it("returns ~/.local/bin/warding when bundled paths don't exist", () => {
    const localBin = path.join(HOME, ".local", "bin", "warding");
    const fakeFs = only(localBin);
    const result = findWardingBin(fakeFs, fakeOs, path, RESOURCES, DIRNAME);
    assert.equal(result, localBin);
  });

  it("returns ~/.warding-app/.venv/bin/warding when only venv binary exists", () => {
    const venvBin = path.join(HOME, ".warding-app", ".venv", "bin", "warding");
    const fakeFs = only(venvBin);
    const result = findWardingBin(fakeFs, fakeOs, path, RESOURCES, DIRNAME);
    assert.equal(result, venvBin);
  });

  it("returns ../bin/warding relative to dirname when only that path exists", () => {
    const binPath = path.resolve(DIRNAME, "..", "bin", "warding");
    const fakeFs = only(binPath);
    const result = findWardingBin(fakeFs, fakeOs, path, RESOURCES, DIRNAME);
    assert.equal(result, binPath);
  });

  it("falls back to bare 'warding' when no candidates are executable (POSIX)", () => {
    const result = findWardingBin(none, fakeOs, path, RESOURCES, DIRNAME, "x64", false);
    assert.equal(result, "warding");
  });

  it("falls back to bare 'warding.exe' when no candidates are executable (Windows)", () => {
    const result = findWardingBin(none, fakeOs, path, RESOURCES, DIRNAME, "x64", true);
    assert.equal(result, "warding.exe");
  });

  it("finds the venv Scripts\\warding.exe two levels up from electron/ on Windows", () => {
    const venvExe = path.resolve(DIRNAME, "..", "..", ".venv", "Scripts", "warding.exe");
    const fakeFs = only(venvExe);
    const result = findWardingBin(fakeFs, fakeOs, path, RESOURCES, DIRNAME, "x64", true);
    assert.equal(result, venvExe);
  });

  it("finds the bundled Windows backend Scripts\\warding.exe on Windows", () => {
    const bundledExe = path.join(
      RESOURCES, "backend-dist", "warding-backend", "Scripts", "warding.exe"
    );
    const fakeFs = only(bundledExe);
    const result = findWardingBin(fakeFs, fakeOs, path, RESOURCES, DIRNAME, "x64", true);
    assert.equal(result, bundledExe);
  });

  // A real Windows bundle contains BOTH launchers: build-desktop.sh writes
  // bin\warding.cmd, and the `pip install` that populates the tree also drops
  // a console-script Scripts\warding.exe. Every Windows case above uses
  // only() -- a one-candidate world -- so none of them could express which of
  // the two wins. That gap let the two swap places and reach a nightly, where
  // the build-time resolver gate failed with "the builder output layout and
  // find-bin.js candidate list have drifted apart".
  const present = (...targets) => {
    const set = new Set(targets.map((t) => path.resolve(t)));
    return {
      accessSync: (p) => {
        if (set.has(path.resolve(p))) return;
        const e = new Error("ENOENT");
        e.code = "ENOENT";
        throw e;
      },
      constants: { X_OK: fs.constants.X_OK },
    };
  };

  it("prefers the relocatable bin\\warding.cmd over the bundle's Scripts\\warding.exe", () => {
    // THE REGRESSION. pip's console-script .exe embeds the ABSOLUTE interpreter
    // path of the machine that built it (distlib), so inside a shipped bundle it
    // points at a build-agent path like D:\a\Warding\... that does not exist on
    // the user's machine. The .cmd shim resolves the interpreter through %~dp0
    // and is the only relocatable launcher of the two -- so it must win whenever
    // both are present, which in a real bundle is always.
    const cmd = path.join(RESOURCES, "backend-dist", "warding-backend", "bin", "warding.cmd");
    const exe = path.join(RESOURCES, "backend-dist", "warding-backend", "Scripts", "warding.exe");
    const result = findWardingBin(present(cmd, exe), fakeOs, path, RESOURCES, DIRNAME, "x64", true);
    assert.equal(result, cmd);
  });

  it("prefers the bundle's Scripts\\warding.exe over a user-level install", () => {
    // A packaged app must run the backend it shipped with, never whatever
    // happens to be installed on the machine.
    const exe = path.join(RESOURCES, "backend-dist", "warding-backend", "Scripts", "warding.exe");
    const userLocal = path.join(HOME, ".local", "bin", "warding.exe");
    const result = findWardingBin(
      present(exe, userLocal), fakeOs, path, RESOURCES, DIRNAME, "x64", true
    );
    assert.equal(result, exe);
  });

  it("still finds a user-level warding.exe when nothing is bundled", () => {
    const userLocal = path.join(HOME, ".local", "bin", "warding.exe");
    const result = findWardingBin(
      present(userLocal), fakeOs, path, RESOURCES, DIRNAME, "x64", true
    );
    assert.equal(result, userLocal);
  });

  it("does not probe Windows .exe candidates on POSIX", () => {
    const probed = [];
    const fakeFs = {
      accessSync: (p) => { probed.push(p); throw new Error("ENOENT"); },
      constants: { X_OK: fs.constants.X_OK },
    };
    findWardingBin(fakeFs, fakeOs, path, RESOURCES, DIRNAME, "x64", false);
    assert.deepStrictEqual(probed.filter((p) => p.endsWith(".exe")), []);
  });

  it("returns first match when multiple candidates exist", () => {
    const bundled = path.join(RESOURCES, "backend-dist", "warding-backend", "bin", "warding");
    const localBin = path.join(HOME, ".local", "bin", "warding");
    const fakeFs = {
      accessSync: (p) => { if (p !== bundled && p !== localBin) throw new Error("ENOENT"); },
      constants: { X_OK: fs.constants.X_OK },
    };
    const result = findWardingBin(fakeFs, fakeOs, path, RESOURCES, DIRNAME);
    assert.equal(result, bundled);
  });

  it("handles resourcesPath being undefined", () => {
    const localBin = path.join(HOME, ".local", "bin", "warding");
    const fakeFs = only(localBin);
    const result = findWardingBin(fakeFs, fakeOs, path, undefined, DIRNAME);
    assert.equal(result, localBin);
  });

  it("resolves dirname-relative dev path correctly", () => {
    const devBin = path.resolve(DIRNAME, "backend-dist", "warding-backend", "bin", "warding");
    const fakeFs = only(devBin);
    const result = findWardingBin(fakeFs, fakeOs, path, RESOURCES, DIRNAME);
    assert.equal(result, devBin);
  });

  it("skips candidates that throw non-ENOENT errors (e.g. EACCES)", () => {
    const venvBin = path.join(HOME, ".warding-app", ".venv", "bin", "warding");
    const fakeFs = {
      accessSync: (p) => { if (p !== venvBin) throw new Error("EACCES"); },
      constants: { X_OK: fs.constants.X_OK },
    };
    const result = findWardingBin(fakeFs, fakeOs, path, RESOURCES, DIRNAME);
    assert.equal(result, venvBin);
  });

  // Universal-bundle layout: arch-suffixed backend trees under backend-dist/.
  const archBin = (arch) =>
    path.join(RESOURCES, "backend-dist", `warding-backend-${arch}`, "bin", "warding");
  const armBackend = archBin("arm64");
  const x64Backend = archBin("x64");

  const both = (targets) => ({
    accessSync: (p) => { if (!targets.includes(p)) throw new Error("ENOENT"); },
    constants: { X_OK: fs.constants.X_OK },
  });

  it("picks the arm64 backend tree for arch 'arm64' when both suffixed dirs exist", () => {
    const fakeFs = both([armBackend, x64Backend]);
    const result = findWardingBin(fakeFs, fakeOs, path, RESOURCES, DIRNAME, "arm64");
    assert.equal(result, armBackend);
  });

  it("picks the x64 backend tree for arch 'x64' when both suffixed dirs exist", () => {
    const fakeFs = both([armBackend, x64Backend]);
    const result = findWardingBin(fakeFs, fakeOs, path, RESOURCES, DIRNAME, "x64");
    assert.equal(result, x64Backend);
  });

  it("prefers the arch-suffixed tree over the unsuffixed layout when both exist", () => {
    const unsuffixed = path.join(RESOURCES, "backend-dist", "warding-backend", "bin", "warding");
    const fakeFs = both([armBackend, unsuffixed]);
    const result = findWardingBin(fakeFs, fakeOs, path, RESOURCES, DIRNAME, "arm64");
    assert.equal(result, armBackend);
  });

  it("falls back to the unsuffixed layout when arch-suffixed dirs are absent", () => {
    const unsuffixed = path.join(RESOURCES, "backend-dist", "warding-backend", "bin", "warding");
    const fakeFs = only(unsuffixed);
    const result = findWardingBin(fakeFs, fakeOs, path, RESOURCES, DIRNAME, "arm64");
    assert.equal(result, unsuffixed);
  });

  it("skips arch-suffixed candidates cleanly for an unmapped arch (e.g. 'ia32')", () => {
    const probed = [];
    const unsuffixed = path.join(RESOURCES, "backend-dist", "warding-backend", "bin", "warding");
    const fakeFs = {
      accessSync: (p) => { probed.push(p); if (p !== unsuffixed) throw new Error("ENOENT"); },
      constants: { X_OK: fs.constants.X_OK },
    };
    const result = findWardingBin(fakeFs, fakeOs, path, RESOURCES, DIRNAME, "ia32");
    assert.equal(result, unsuffixed);
    assert.deepStrictEqual(probed.filter((p) => p.includes("warding-backend-")), []);
  });
});
