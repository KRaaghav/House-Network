"""
Tests for the house lab. To run them:

  pip install pytest
  pytest

None of them change the lab file.
"""

import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))

import floorplan                                    # noqa: E402
import houselayout                                  # noqa: E402
import pktconfig                                    # noqa: E402
import pkticons                                     # noqa: E402

VLAN = {"FAMILY": "10", "SMART-HOME": "20", "GUEST": "30"}


def cables():
    """[(device, port, device, port)] of every cable in the lab."""
    xml = pktconfig.Lab().xml()
    names = {re.search(r"save-ref-id:\d+", b).group(0): re.search(r"<NAME[^>]*>([^<]*)", b).group(1)
             for b in re.findall(r"<DEVICE>.*?</DEVICE>", xml, re.S)}
    found = []
    for link in re.findall(r"<LINK>.*?</LINK>", xml, re.S):
        (a, a_port), (b, b_port) = re.findall(r"<(?:FROM|TO)>([^<]*)</(?:FROM|TO)>\s*<PORT>([^<]*)</PORT>", link)
        found.append((names[a], a_port, names[b], b_port))
    return found


def port_lines(config, port):
    at = config.index("interface " + port)
    return [l.strip() for l in config[at + 1:pktconfig.section_end(config, at)]]


def test_configs_in_the_lab_match_the_configs_folder():
    assert pktconfig.check(pktconfig.LAB) == 0


def test_every_device_is_in_the_right_vlan():
    lab = pktconfig.Lab()
    rows = {row["name"]: row for row in houselayout.inventory()}
    seen = set()
    for a, a_port, b, b_port in cables():
        for switch, port, host in ((a, a_port, b), (b, b_port, a)):
            if switch.startswith("SW-") and host in rows and not host.startswith(("SW-", "HOME")):
                assert f"switchport access vlan {VLAN[rows[host]['network']]}" in port_lines(lab.config(switch), port), host
                seen.add(host)
    assert seen == {name for name, row in rows.items() if row["network"] in VLAN}


def test_unused_switch_ports_are_shut_down():
    lab = pktconfig.Lab()
    used = {(a, a_port) for a, a_port, b, b_port in cables()} | {(b, b_port) for a, a_port, b, b_port in cables()}
    for switch in ("SW-DOWN", "SW-UP"):
        config = lab.config(switch)
        for line in config:
            if re.fullmatch(r"interface (Fast|Gigabit)Ethernet0/\d+", line) and (switch, line[10:]) not in used:
                assert "shutdown" in port_lines(config, line[10:]), (switch, line)


def test_the_house_is_cabled_router_to_switch_to_switch():
    links = {tuple(sorted((a, b))) for a, a_port, b, b_port in cables()}
    assert ("HOME-RTR", "SW-DOWN") in links and ("SW-DOWN", "SW-UP") in links and ("HOME-RTR", "ISP") in links


def test_floor_plan_has_no_overlaps_and_everything_has_a_room():
    plan = houselayout.plan()
    solid = plan.floors + plan.walls
    for i, a in enumerate(solid):
        for b in solid[i + 1:]:
            assert not (a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]), (a, b)
    assert {row["name"] for row in houselayout.inventory()} <= set(plan.where)
    places = list(plan.where.values())
    assert len(set(places)) == len(places)


def test_pictures_and_the_saved_floor_plan_are_up_to_date():
    for row in houselayout.inventory():
        if row["type"] not in ("PC", "router 2911", "switch 2960"):
            assert row["type"] in pkticons.ICONS, row["name"]
    with open(os.path.join(ROOT, "floorplan.svg")) as f:
        assert f.read() == floorplan.svg()
