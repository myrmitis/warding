const { describe, it } = require("node:test");
const assert = require("node:assert/strict");
const path = require("path");
const fs = require("fs");
const { findJunctionBin } = require("../find-bin");

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

describe("findJunctionBin", () => {
  it("returns the bundled backend launcher (backend-dist/.../bin/junction) when it exists", () => {
    const venvLayout = path.join(RESOURCES, "backend-dist", "junction-backend", "bin", "junction");
    const fakeFs = only(venvLayout);
    const result = findJunctionBin(fakeFs, fakeOs, path, RESOURCES, DIRNAME);
    assert.equal(result, venvLayout);
  });

  it("returns ~/.local/bin/junction when bundled paths don't exist", () => {
    const localBin = path.join(HOME, ".local", "bin", "junction");
    const fakeFs = only(localBin);
    const result = findJunctionBin(fakeFs, fakeOs, path, RESOURCES, DIRNAME);
    assert.equal(result, localBin);
  });

  it("returns ~/.junction-app/.venv/bin/junction when only venv binary exists", () => {
    const venvBin = path.join(HOME, ".junction-app", ".venv", "bin", "junction");
    const fakeFs = only(venvBin);
    const result = findJunctionBin(fakeFs, fakeOs, path, RESOURCES, DIRNAME);
    assert.equal(result, venvBin);
  });

  it("returns ../bin/junction relative to dirname when only that path exists", () => {
    const binPath = path.resolve(DIRNAME, "..", "bin", "junction");
    const fakeFs = only(binPath);
    const result = findJunctionBin(fakeFs, fakeOs, path, RESOURCES, DIRNAME);
    assert.equal(result, binPath);
  });

  it("falls back to bare 'junction' when no candidates are executable (POSIX)", () => {
    const result = findJunctionBin(none, fakeOs, path, RESOURCES, DIRNAME, "x64", false);
    assert.equal(result, "junction");
  });

  it("falls back to bare 'junction.exe' when no candidates are executable (Windows)", () => {
    const result = findJunctionBin(none, fakeOs, path, RESOURCES, DIRNAME, "x64", true);
    assert.equal(result, "junction.exe");
  });

  it("finds the venv Scripts\\junction.exe two levels up from electron/ on Windows", () => {
    const venvExe = path.resolve(DIRNAME, "..", "..", ".venv", "Scripts", "junction.exe");
    const fakeFs = only(venvExe);
    const result = findJunctionBin(fakeFs, fakeOs, path, RESOURCES, DIRNAME, "x64", true);
    assert.equal(result, venvExe);
  });

  it("finds the bundled Windows backend Scripts\\junction.exe on Windows", () => {
    const bundledExe = path.join(
      RESOURCES, "backend-dist", "junction-backend", "Scripts", "junction.exe"
    );
    const fakeFs = only(bundledExe);
    const result = findJunctionBin(fakeFs, fakeOs, path, RESOURCES, DIRNAME, "x64", true);
    assert.equal(result, bundledExe);
  });

  // A real Windows bundle contains BOTH launchers: build-desktop.sh writes
  // bin\junction.cmd, and the `pip install` that populates the tree also drops
  // a console-script Scripts\junction.exe. Every Windows case above uses
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

  it("prefers the relocatable bin\\junction.cmd over the bundle's Scripts\\junction.exe", () => {
    // THE REGRESSION. pip's console-script .exe embeds the ABSOLUTE interpreter
    // path of the machine that built it (distlib), so inside a shipped bundle it
    // points at a build-agent path like D:\a\Junction\... that does not exist on
    // the user's machine. The .cmd shim resolves the interpreter through %~dp0
    // and is the only relocatable launcher of the two -- so it must win whenever
    // both are present, which in a real bundle is always.
    const cmd = path.join(RESOURCES, "backend-dist", "junction-backend", "bin", "junction.cmd");
    const exe = path.join(RESOURCES, "backend-dist", "junction-backend", "Scripts", "junction.exe");
    const result = findJunctionBin(present(cmd, exe), fakeOs, path, RESOURCES, DIRNAME, "x64", true);
    assert.equal(result, cmd);
  });

  it("prefers the bundle's Scripts\\junction.exe over a user-level install", () => {
    // A packaged app must run the backend it shipped with, never whatever
    // happens to be installed on the machine.
    const exe = path.join(RESOURCES, "backend-dist", "junction-backend", "Scripts", "junction.exe");
    const userLocal = path.join(HOME, ".local", "bin", "junction.exe");
    const result = findJunctionBin(
      present(exe, userLocal), fakeOs, path, RESOURCES, DIRNAME, "x64", true
    );
    assert.equal(result, exe);
  });

  it("still finds a user-level junction.exe when nothing is bundled", () => {
    const userLocal = path.join(HOME, ".local", "bin", "junction.exe");
    const result = findJunctionBin(
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
    findJunctionBin(fakeFs, fakeOs, path, RESOURCES, DIRNAME, "x64", false);
    assert.deepStrictEqual(probed.filter((p) => p.endsWith(".exe")), []);
  });

  it("returns first match when multiple candidates exist", () => {
    const bundled = path.join(RESOURCES, "backend-dist", "junction-backend", "bin", "junction");
    const localBin = path.join(HOME, ".local", "bin", "junction");
    const fakeFs = {
      accessSync: (p) => { if (p !== bundled && p !== localBin) throw new Error("ENOENT"); },
      constants: { X_OK: fs.constants.X_OK },
    };
    const result = findJunctionBin(fakeFs, fakeOs, path, RESOURCES, DIRNAME);
    assert.equal(result, bundled);
  });

  it("handles resourcesPath being undefined", () => {
    const localBin = path.join(HOME, ".local", "bin", "junction");
    const fakeFs = only(localBin);
    const result = findJunctionBin(fakeFs, fakeOs, path, undefined, DIRNAME);
    assert.equal(result, localBin);
  });

  it("resolves dirname-relative dev path correctly", () => {
    const devBin = path.resolve(DIRNAME, "backend-dist", "junction-backend", "bin", "junction");
    const fakeFs = only(devBin);
    const result = findJunctionBin(fakeFs, fakeOs, path, RESOURCES, DIRNAME);
    assert.equal(result, devBin);
  });

  it("skips candidates that throw non-ENOENT errors (e.g. EACCES)", () => {
    const venvBin = path.join(HOME, ".junction-app", ".venv", "bin", "junction");
    const fakeFs = {
      accessSync: (p) => { if (p !== venvBin) throw new Error("EACCES"); },
      constants: { X_OK: fs.constants.X_OK },
    };
    const result = findJunctionBin(fakeFs, fakeOs, path, RESOURCES, DIRNAME);
    assert.equal(result, venvBin);
  });

  // Universal-bundle layout: arch-suffixed backend trees under backend-dist/.
  const archBin = (arch) =>
    path.join(RESOURCES, "backend-dist", `junction-backend-${arch}`, "bin", "junction");
  const armBackend = archBin("arm64");
  const x64Backend = archBin("x64");

  const both = (targets) => ({
    accessSync: (p) => { if (!targets.includes(p)) throw new Error("ENOENT"); },
    constants: { X_OK: fs.constants.X_OK },
  });

  it("picks the arm64 backend tree for arch 'arm64' when both suffixed dirs exist", () => {
    const fakeFs = both([armBackend, x64Backend]);
    const result = findJunctionBin(fakeFs, fakeOs, path, RESOURCES, DIRNAME, "arm64");
    assert.equal(result, armBackend);
  });

  it("picks the x64 backend tree for arch 'x64' when both suffixed dirs exist", () => {
    const fakeFs = both([armBackend, x64Backend]);
    const result = findJunctionBin(fakeFs, fakeOs, path, RESOURCES, DIRNAME, "x64");
    assert.equal(result, x64Backend);
  });

  it("prefers the arch-suffixed tree over the unsuffixed layout when both exist", () => {
    const unsuffixed = path.join(RESOURCES, "backend-dist", "junction-backend", "bin", "junction");
    const fakeFs = both([armBackend, unsuffixed]);
    const result = findJunctionBin(fakeFs, fakeOs, path, RESOURCES, DIRNAME, "arm64");
    assert.equal(result, armBackend);
  });

  it("falls back to the unsuffixed layout when arch-suffixed dirs are absent", () => {
    const unsuffixed = path.join(RESOURCES, "backend-dist", "junction-backend", "bin", "junction");
    const fakeFs = only(unsuffixed);
    const result = findJunctionBin(fakeFs, fakeOs, path, RESOURCES, DIRNAME, "arm64");
    assert.equal(result, unsuffixed);
  });

  it("skips arch-suffixed candidates cleanly for an unmapped arch (e.g. 'ia32')", () => {
    const probed = [];
    const unsuffixed = path.join(RESOURCES, "backend-dist", "junction-backend", "bin", "junction");
    const fakeFs = {
      accessSync: (p) => { probed.push(p); if (p !== unsuffixed) throw new Error("ENOENT"); },
      constants: { X_OK: fs.constants.X_OK },
    };
    const result = findJunctionBin(fakeFs, fakeOs, path, RESOURCES, DIRNAME, "ia32");
    assert.equal(result, unsuffixed);
    assert.deepStrictEqual(probed.filter((p) => p.includes("junction-backend-")), []);
  });
});
