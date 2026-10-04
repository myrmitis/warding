"""Composed harness + model plane snapshot."""

from __future__ import annotations

import argparse
import io
import json
import socket
from collections.abc import Iterator
from dataclasses import dataclass

import pytest

from junction.acp.types import ACP_BACKEND_AUTO, ACP_BACKEND_CURSOR
from junction.cli_doctor import _doctor, _doctor_planes
from junction.constants import CLI_BIN, PRODUCT_NAME
from junction.model_router import probe
from junction.planes import api_planes, harness_inventory, run_planes_command, snapshot_planes


@dataclass(frozen=True)
class PlanePorts:
    router: int
    gateway: int


def _bind_refusing_port() -> socket.socket:
    """Hold a loopback port without listening on it.

    A connect to a bound, non-listening TCP port is refused, and while this
    socket stays open no other listener can take the port, so the probe's
    answer depends only on the test.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((probe.LOOPBACK_HOST, 0))
    except OSError:
        sock.close()
        raise
    return sock


@pytest.fixture(autouse=True)
def plane_ports(monkeypatch: pytest.MonkeyPatch) -> Iterator[PlanePorts]:
    """Point every model-plane probe at ports this test owns and nobody answers.

    Several surfaces here (doctor, the compose banner, ``/api/planes``) probe
    with no explicit port, which resolves to the default loopback ports. Those
    are host state: a real ``junction up``, or an embedded catalog listener an
    earlier test on the same worker left running, turns "down" into "built-in
    catalog" and the verdict into a function of test order. The port env
    overrides the probe already honours take the host out of the answer.
    """
    with _bind_refusing_port() as router, _bind_refusing_port() as gateway:
        ports = PlanePorts(router.getsockname()[1], gateway.getsockname()[1])
        for name in probe._ROUTER_PORT_ENV:
            monkeypatch.setenv(name, str(ports.router))
        for name in probe._GATEWAY_PORT_ENV:
            monkeypatch.setenv(name, str(ports.gateway))
        yield ports


def test_harness_inventory_marks_kiro_optional() -> None:
    rows = harness_inventory(which=lambda _name: None, env={})
    labels = [row["id"] for row in rows]
    assert labels[-1] == "kiro-cli"
    kiro = rows[-1]
    assert kiro["optional"] is True
    assert kiro["available"] is False
    assert ACP_BACKEND_CURSOR in labels


def test_snapshot_degrades_when_nothing_is_installed(plane_ports: PlanePorts) -> None:
    snap = snapshot_planes(
        which=lambda _name: None,
        env={},
        router_port=plane_ports.router,
        gateway_port=plane_ports.gateway,
    )
    assert snap["product"] == PRODUCT_NAME
    assert snap["cli"] == CLI_BIN
    assert snap["harness"]["default"] == ACP_BACKEND_AUTO
    assert snap["harness"]["selected"] == ""
    assert "kiro_cli" not in snap["harness"]
    assert snap["model"]["status"] == "unreachable"
    assert snap["gateway"]["status"] == "ok"
    assert snap["code"] == "ok"
    roles = {row["role"]: row["cost_class"] for row in snap["roles"]["roles"]}
    assert roles["orchestration"] == "economy"
    assert roles["planning"] == "capable"
    assert roles["execution"] == "standard"


def test_cli_planes_prints_human_copy_by_default(
    capsys: pytest.CaptureFixture[str], plane_ports: PlanePorts
) -> None:
    args = argparse.Namespace(router_port=plane_ports.router, as_json=False)
    run_planes_command(args)
    out = capsys.readouterr().out
    assert "Warding planes" in out
    assert "never paste provider keys" in out
    assert "sidecar injects" not in out
    assert "orchestration=economy" in out
    last = out.strip().splitlines()[-1]
    with pytest.raises(json.JSONDecodeError):
        json.loads(last)


def test_cli_planes_json_flag_is_machine_only(
    capsys: pytest.CaptureFixture[str], plane_ports: PlanePorts
) -> None:
    args = argparse.Namespace(router_port=plane_ports.router, as_json=True)
    run_planes_command(args)
    out = capsys.readouterr().out
    assert "Warding planes" not in out
    payload = json.loads(out.strip())
    assert payload["cli"] == "warding"
    assert "kiro_cli" not in payload["harness"]
    assert payload["roles"]["code"] == "ok"


@pytest.fixture
def _closed_plane_ports(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the doctor's probes at a closed port, like the tests above.

    The doctor takes no port arguments, so without this it probes the real
    loopback defaults, and any process listening there (another test's gateway
    bringing up the embedded catalog on 4202, a developer's own Junction) turns
    "down" into "built-in catalog".
    """
    from junction.model_router.probe import _GATEWAY_PORT_ENV, _ROUTER_PORT_ENV

    for name in (*_ROUTER_PORT_ENV, *_GATEWAY_PORT_ENV):
        monkeypatch.setenv(name, "9")


@pytest.mark.usefixtures("_closed_plane_ports")
def test_doctor_planes_never_fails(capsys: pytest.CaptureFixture[str]) -> None:
    _doctor_planes()
    out = capsys.readouterr().out
    assert "Planes" in out
    assert "vendor CLI optional" in out
    assert "starts with junction up" in out
    assert "orchestration=economy" in out
    assert "never paste provider keys" in out
    assert "sidecar injects" not in out


@pytest.mark.usefixtures("_closed_plane_ports")
def test_doctor_quick_skips_the_full_probe(capsys: pytest.CaptureFixture[str]) -> None:
    _doctor(quick=True)
    out = capsys.readouterr().out
    assert "Quick compose" in out
    assert "Planes" in out
    assert "Platform" not in out
    assert "Dependencies" not in out
    assert "junction doctor" in out


@pytest.mark.asyncio
async def test_api_planes_always_200() -> None:
    from aiohttp.test_utils import make_mocked_request

    request = make_mocked_request("GET", "/api/planes")
    resp = await api_planes(request)
    assert resp.status == 200
    payload = json.loads(resp.body.decode())
    assert payload["cli"] == CLI_BIN
    assert payload["code"] == "ok"
    assert payload["gateway"]["status"] == "ok"
    assert "roles" in payload
    assert "kiro_cli" not in payload["harness"]


def test_human_planes_format_is_shared(plane_ports: PlanePorts) -> None:
    from junction.planes import format_human_planes

    snap = snapshot_planes(
        which=lambda _name: None,
        env={},
        router_port=plane_ports.router,
        gateway_port=plane_ports.gateway,
    )
    text = format_human_planes(snap, heading="Planes")
    assert text.startswith("Planes\n")
    assert "vendor CLI optional" in text
    assert "starts with junction up" in text
    assert "orchestration=economy" in text
    assert "never paste provider keys" in text


def test_compose_banner_writes_the_given_stream() -> None:
    from junction.planes import print_compose_banner

    buf = io.StringIO()
    print_compose_banner(stream=buf)
    text = buf.getvalue()
    assert "Warding compose" in text
    assert "vendor CLI optional" in text
