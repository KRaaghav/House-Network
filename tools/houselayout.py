#!/usr/bin/env python3
"""
houselayout.py - draw the house on the canvas of the Packet Tracer lab

It turns the logical view into a floor plan of a two floor house, without touching any
device config:

  - puts every device in its room: the router and the downstairs switch in the closet
    under the stairs, the upstairs switch in the closet in the upstairs hall, the TVs,
    laptops, cameras and the fridge where they are in a real house
  - draws the floors, the walls with doors and windows, and the things that make it a
    house: beds, sofa, car, kitchen counter, the pool and the trampoline in the backyard
  - gives the smart TV, fridge, doorbell and the other things their own picture (pkticons.py)
  - writes the text notes on the canvas, and all of them into the lab description (the "i"
    button in Packet Tracer)

  python3 houselayout.py                 draw the house
  python3 houselayout.py --dry-run       only say what would move

Close the lab in Packet Tracer first. A copy of the lab from before is kept in
../changes/backups. Only uses the Python standard library, nothing to install.
"""

import base64
import csv
import html
import os
import re
import sys
import uuid

import pktfile
import pkticons
from pktconfig import HERE, LAB, Problem, backup_lab, packet_tracer_is_open

# ---------------------------------------------------------------- sizes and colours
# All numbers are pixels on the canvas. A device position is the middle of its icon.

WALL = 14
LEFT, TOP = 80, 20
ROW_H = 420                     # one row of rooms
SIDE_W, MIDDLE_W, BIG_W = 520, 300, 720   # the three rooms of a row, left to right
FLOOR_GAP = 220                 # between the downstairs plan and the upstairs plan
LINE = 28                       # height of one line of a note

BRICK = (70, 78, 92)
GREY, ROAD, PATH, LINE_WHITE = (232, 232, 232), (150, 154, 160), (222, 214, 200), (255, 255, 255)
GRASS, TREE, WATER, WINDOW = (196, 232, 176), (96, 168, 92), (120, 196, 240), (176, 222, 250)
HALL, CLOSET, TILE = (240, 240, 236), (255, 214, 160), (226, 238, 244)
GARAGE, ENTRY, LIVING, KITCHEN, OFFICE = (220, 220, 214), (250, 236, 214), (255, 246, 200), (255, 232, 210), (214, 245, 224)
KID1, KID2, MAIN, GUEST = (214, 230, 255), (250, 220, 240), (232, 222, 255), (255, 240, 214)
WOOD, SOFA, BED, PILLOW, CAR, RUG = (214, 180, 140), (110, 130, 170), (150, 170, 220), (255, 255, 255), (220, 70, 60), (240, 200, 120)


def inventory():
    with open(os.path.join(HERE, "inventory.csv"), newline="") as f:
        return list(csv.DictReader(f))


def place(room):
    """[(name, type)] of what inventory.csv puts in a room."""
    return [(row["name"], row["type"]) for row in inventory() if row["location"] == room]


# ---------------------------------------------------------------- drawing

class Plan:
    """Everything on the canvas. floors never lie on top of each other, so it does not matter
    in which order Packet Tracer draws them. extras (desks, lockers, trees) are small things
    drawn on a floor, ovals are the round ones."""

    def __init__(self):
        self.floors = []        # (left, top, right, bottom, colour)
        self.walls = []
        self.extras = []
        self.ovals = []
        self.notes = []         # (x, y, text)
        self.where = {}         # device name: (x, y)
        self.areas = {}         # a name like "E wing hall": (left, top, right, bottom), for floorplan.py

    def floor(self, left, top, right, bottom, colour):
        self.floors.append((left, top, right, bottom, colour))

    def extra(self, left, top, right, bottom, colour):
        self.extras.append((left, top, right, bottom, colour))

    def oval(self, left, top, right, bottom, colour):
        self.ovals.append((left, top, right, bottom, colour))

    def note(self, x, y, text):
        self.notes.append((x, y, text))

    def put(self, name, x, y):
        self.where[name] = (round(x), round(y))

    def title(self, box, text):
        """A note in the bottom left corner of a room."""
        self.note(box[0] + 14, box[3] - LINE * len(text.split("\n")) - 12, text)

    def building(self, floors):
        """Add the floors of one building and put walls everywhere between and around them.
        A floor that is only as thick as a wall is a door: it makes a gap in the wall."""
        inside = [f for f in floors if min(f[2] - f[0], f[3] - f[1]) > WALL]
        left = min(f[0] for f in inside) - WALL
        top = min(f[1] for f in inside) - WALL
        right = max(f[2] for f in inside) + WALL
        bottom = max(f[3] for f in inside) + WALL
        self.floors += floors
        self.walls += [piece + (BRICK,) for piece in leftover((left, top, right, bottom), floors)]
        return left, top, right, bottom


def leftover(box, holes):
    """The part of a box that no hole covers, cut into rectangles that do not overlap."""
    xs = sorted({box[0], box[2]} | {v for h in holes for v in (h[0], h[2]) if box[0] < v < box[2]})
    ys = sorted({box[1], box[3]} | {v for h in holes for v in (h[1], h[3]) if box[1] < v < box[3]})
    rows = []
    for top, bottom in zip(ys, ys[1:]):
        runs = []
        for left, right in zip(xs, xs[1:]):
            x, y = (left + right) / 2, (top + bottom) / 2
            if any(h[0] <= x < h[2] and h[1] <= y < h[3] for h in holes):
                continue
            if runs and runs[-1][1] == left:
                runs[-1] = (runs[-1][0], right)
            else:
                runs.append((left, right))
        rows.append((top, bottom, runs))
    found = []
    open_runs = {}              # (left, right): top of the rectangle that is still growing
    for top, bottom, runs in rows + [(box[3], box[3], [])]:
        for run in list(open_runs):
            if run not in runs:
                found.append((run[0], open_runs.pop(run), run[1], top))
        for run in runs:
            open_runs.setdefault(run, top)
    return found




def plan():
    """Work out where everything goes. Downstairs on the left, upstairs on the right, the
    street with the internet at the top, the backyard at the bottom."""
    p = Plan()
    gx, gy = LEFT + WALL, TOP + 330                    # top left corner of the first room downstairs
    ux = gx + SIDE_W + MIDDLE_W + BIG_W + 4 * WALL + FLOOR_GAP
    row2 = gy + ROW_H + WALL

    def columns(x):
        return x, x + SIDE_W + WALL, x + SIDE_W + MIDDLE_W + 2 * WALL

    def room(name, box, colour, title):
        p.areas[name] = box
        p.title(box, title)
        return box + (colour,)

    def devices(room_name, spots):
        for (name, kind), spot in zip(place(room_name), spots):
            p.put(name, *spot)

    # ---------------- downstairs
    a, b, c = columns(gx)
    garage = (a, gy, a + SIDE_W, gy + ROW_H)
    entry = (b, gy, b + MIDDLE_W, gy + ROW_H)
    living = (c, gy, c + BIG_W, gy + ROW_H)
    kitchen = (a, row2, a + SIDE_W, row2 + ROW_H)
    hall = (b, row2, b + MIDDLE_W, row2 + 220)
    closet = (b, row2 + 234, b + MIDDLE_W, row2 + ROW_H)
    office = (c, row2, c + BIG_W, row2 + ROW_H)
    down = [room("Garage", garage, GARAGE, "Garage"), room("Entry", entry, ENTRY, "Entry"),
            room("Living room", living, LIVING, "Living room"), room("Kitchen", kitchen, KITCHEN, "Kitchen"),
            hall + (HALL,), room("Network closet", closet, CLOSET, "Network closet"),
            room("Office", office, OFFICE, "Office")]
    down += [(a + 60, gy - WALL, a + 460, gy, PATH),                         # garage door
             (b + 110, gy - WALL, b + 190, gy, HALL),                        # front door
             (b + MIDDLE_W, gy + 160, c, gy + 260, HALL),                    # entry - living room
             (b + 100, gy + ROW_H, b + 200, row2, HALL),                     # entry - hall
             (a + SIDE_W, row2 + 60, b, row2 + 160, HALL),                   # kitchen - hall
             (b + MIDDLE_W, row2 + 60, c, row2 + 160, HALL),                 # hall - office
             (b + 180, hall[3], b + 260, closet[1], HALL),                   # hall - closet
             (a + SIDE_W, gy + 160, b, gy + 240, HALL),                      # garage - entry
             (a + 360, kitchen[3], a + 440, kitchen[3] + WALL, HALL),        # back door
             (c + 120, gy - WALL, c + 300, gy, WINDOW), (c + 420, gy - WALL, c + 600, gy, WINDOW),
             (a + 80, kitchen[3], a + 260, kitchen[3] + WALL, WINDOW),
             (c + BIG_W, row2 + 120, c + BIG_W + WALL, row2 + 300, WINDOW),
             (c + BIG_W, gy + 120, c + BIG_W + WALL, gy + 300, WINDOW)]
    house_down = p.building(down)

    devices("Garage", [(a + 440, gy + 70)])
    p.extra(a + 70, gy + 110, a + 250, gy + 330, CAR)                       # the car, from above
    p.extra(a + 90, gy + 140, a + 230, gy + 180, WINDOW)
    p.extra(a + 90, gy + 260, a + 230, gy + 295, WINDOW)
    p.extra(a + 330, gy + 330, a + 500, gy + 370, WOOD)                     # workbench
    devices("Entry", [(b + 60, gy + 70), (b + 240, gy + 70), (b + 150, gy + 260)])
    p.oval(b + 80, gy + 110, b + 220, gy + 190, RUG)
    devices("Living room", [(c + 300, gy + 300), (c + 360, gy + 70), (c + 180, gy + 200), (c + 640, gy + 70)])
    p.extra(c + 230, gy + 130, c + 490, gy + 190, SOFA)                      # sofa, facing the TV
    p.oval(c + 300, gy + 210, c + 420, gy + 250, WOOD)                       # coffee table
    p.extra(c + 240, gy + 270, c + 360, gy + 320, WOOD)                      # desk of the family PC
    devices("Kitchen", [(a + 70, row2 + 90), (a + 300, row2 + 90), (a + 450, row2 + 330)])
    p.extra(a + 120, row2 + 14, a + 470, row2 + 50, WOOD)                    # counter
    p.extra(a + 160, row2 + 170, a + 360, row2 + 230, TILE)                  # island
    p.oval(a + 40, row2 + 260, a + 200, row2 + 360, WOOD)                    # table
    devices("Network closet", [(b + 70, closet[1] + 65), (b + 230, closet[1] + 65)])
    for n in range(6):                                                       # stairs going up
        p.extra(b + 20 + 26 * n, hall[1] + 20, b + 40 + 26 * n, hall[1] + 130, (200, 200, 196))
    p.note(b + 14, hall[1] + 140, "stairs up")
    devices("Office", [(c + 150, row2 + 110), (c + 330, row2 + 110), (c + 600, row2 + 110)])
    p.extra(c + 80, row2 + 150, c + 400, row2 + 200, WOOD)                   # desk
    p.extra(c + 560, row2 + 260, c + 700, row2 + 300, WOOD)                  # bookshelf

    # ---------------- upstairs
    a2, b2, c2 = columns(ux)
    bed1 = (a2, gy, a2 + SIDE_W, gy + ROW_H)
    up_closet = (b2, gy, b2 + MIDDLE_W, gy + 190)
    up_hall = (b2, gy + 204, b2 + MIDDLE_W, gy + ROW_H)
    bed2 = (c2, gy, c2 + BIG_W, gy + ROW_H)
    main = (a2, row2, a2 + SIDE_W, row2 + ROW_H)
    bath = (b2, row2, b2 + MIDDLE_W, row2 + ROW_H)
    guest = (c2, row2, c2 + BIG_W, row2 + ROW_H)
    up = [room("Bedroom 1", bed1, KID1, "Bedroom 1"), room("Upstairs closet", up_closet, CLOSET, "Closet"),
          up_hall + (HALL,), room("Bedroom 2", bed2, KID2, "Bedroom 2"),
          room("Main bedroom", main, MAIN, "Main bedroom"), room("Bathroom", bath, TILE, "Bathroom"),
          room("Guest room", guest, GUEST, "Guest room")]
    up += [(b2 + 180, up_closet[3], b2 + 260, up_hall[1], HALL),            # hall - closet
           (a2 + SIDE_W, gy + 260, b2, gy + 360, HALL),                     # hall - bedroom 1
           (b2 + MIDDLE_W, gy + 260, c2, gy + 360, HALL),                   # hall - bedroom 2
           (a2 + 360, gy + ROW_H, a2 + 460, row2, HALL),                    # bedroom 1 side: main bedroom
           (b2 + 100, gy + ROW_H, b2 + 200, row2, HALL),                    # hall - bathroom
           (c2 + 100, gy + ROW_H, c2 + 200, row2, HALL),                    # bedroom 2 side: guest room
           (a2 + 120, gy - WALL, a2 + 320, gy, WINDOW), (c2 + 200, gy - WALL, c2 + 500, gy, WINDOW),
           (a2 + 150, main[3], a2 + 350, main[3] + WALL, WINDOW), (c2 + 250, guest[3], c2 + 500, guest[3] + WALL, WINDOW)]
    house_up = p.building(up)

    devices("Bedroom 1", [(a2 + 110, gy + 100), (a2 + 290, gy + 100)])
    p.extra(a2 + 50, gy + 140, a2 + 350, gy + 180, WOOD)                    # gaming desk
    p.extra(a2 + 300, gy + 220, a2 + 490, gy + 380, BED)
    p.extra(a2 + 310, gy + 230, a2 + 360, gy + 370, PILLOW)
    devices("Upstairs closet", [(b2 + 150, gy + 80)])
    for n in range(6):
        p.extra(b2 + 20 + 26 * n, up_hall[1] + 20, b2 + 40 + 26 * n, up_hall[1] + 110, (200, 200, 196))
    p.note(b2 + 14, up_hall[1] + 120, "stairs down")
    devices("Bedroom 2", [(c2 + 150, gy + 100), (c2 + 620, gy + 70)])
    p.extra(c2 + 80, gy + 140, c2 + 250, gy + 180, WOOD)
    p.extra(c2 + 420, gy + 200, c2 + 640, gy + 370, BED)
    p.extra(c2 + 430, gy + 210, c2 + 480, gy + 360, PILLOW)
    p.oval(c2 + 250, gy + 250, c2 + 340, gy + 330, (250, 120, 160))         # bean bag
    devices("Main bedroom", [(a2 + 260, row2 + 70), (a2 + 90, row2 + 290), (a2 + 430, row2 + 290)])
    p.extra(a2 + 160, row2 + 150, a2 + 360, row2 + 360, BED)
    p.extra(a2 + 170, row2 + 160, a2 + 350, row2 + 200, PILLOW)
    p.extra(b2 + 30, row2 + 30, b2 + 130, row2 + 230, WATER)                 # bath tub
    p.oval(b2 + 200, row2 + 40, b2 + 260, row2 + 110, (255, 255, 255))      # sink
    devices("Guest room", [(c2 + 150, row2 + 110)])
    p.extra(c2 + 400, row2 + 120, c2 + 620, row2 + 300, BED)
    p.extra(c2 + 410, row2 + 130, c2 + 460, row2 + 290, PILLOW)
    p.extra(c2 + 150, row2 + 220, c2 + 230, row2 + 330, (120, 90, 70))      # suitcase

    right = house_up[2]

    # ---------------- the street, the front yard and the backyard
    internet = (b - 120, TOP, b + 520, TOP + 200)
    p.floor(*internet, GREY)
    p.put("ISP", b + 80, TOP + 100)
    p.put("INET-SRV", b + 360, TOP + 100)
    p.note(internet[0] + 14, TOP + 8, "THE INTERNET (simulated)")
    for road in ((LEFT, TOP + 40, internet[0] - 20, TOP + 160), (internet[2] + 20, TOP + 40, right, TOP + 160)):
        p.floor(*road, ROAD)
        for n in range(int(road[2] - road[0] - 60) // 200):
            p.extra(road[0] + 30 + 200 * n, TOP + 97, road[0] + 130 + 200 * n, TOP + 103, LINE_WHITE)
    p.note(internet[2] + 40, TOP + 46, "Maple Street")
    yard = (LEFT, TOP + 220, house_down[2], house_down[1] - 10)
    driveway = (a + 60, yard[1], a + 460, yard[3])
    walk = (b + 110, yard[1], b + 190, yard[3])
    p.floors += [piece + (GRASS,) for piece in leftover(yard, [driveway, walk])]
    p.floor(*driveway, PATH)
    p.floor(*walk, PATH)
    p.note(c + 20, yard[1] + 10, "DOWNSTAIRS")
    p.note(c2 + 20, yard[1] + 10, "UPSTAIRS (the floor above, drawn next to it)")
    for n in range(3):
        p.oval(c + 380 + 110 * n, yard[1] + 20, c + 450 + 110 * n, yard[1] + 90, TREE)
    back = (LEFT, house_down[3] + 10, house_down[2], house_down[3] + 330)
    pool = (a + 560, back[1] + 60, a + 960, back[1] + 260)
    patio = (a + 300, back[1], a + 500, back[1] + 140)
    p.floors += [piece + (GRASS,) for piece in leftover(back, [pool, patio])]
    p.floor(*pool, WATER)
    p.floor(*patio, PATH)
    p.note(pool[0] + 20, pool[1] + 20, "pool")
    p.oval(c + 380, back[1] + 60, c + 580, back[1] + 260, (60, 70, 84))      # trampoline
    p.oval(c + 400, back[1] + 80, c + 560, back[1] + 240, (120, 130, 150))
    p.note(c + 600, back[1] + 140, "trampoline")
    for n in range(3):
        p.oval(a + 20 + 90 * n, back[1] + 200, a + 100 + 90 * n, back[1] + 280, TREE)
    p.note(LEFT + 14, back[1] + 10, "BACKYARD")
    for n in range(4):                                                       # power strips are devices too: on the garage wall
        p.put(f"Power Distribution Device{n}", a + 300 + 55 * n, gy + 270)

    # ---------------- the notes: under the backyard and under the upstairs plan
    columns_at = {"left": (LEFT, back[3] + 40), "right": (a2, house_up[3] + 40)}
    p.big_notes, p.all_notes = [], []
    for column, text in NOTES:
        p.all_notes.append(text)
        if column in columns_at:
            x, y = columns_at[column]
            p.big_notes.append((x, y, text))
            columns_at[column] = (x, y + LINE * len(text.split("\n")) + 44)
    p.notes += p.big_notes
    p.size = (right + LEFT, max(y for x, y in columns_at.values()) + 40)
    return p


# ---------------------------------------------------------------- the text on the canvas
# (column, text). "left" is under the backyard, "right" under the upstairs plan. A note in
# the column "info" is only in the lab description, so the house stays easy to read.

NOTES = [
    ("left", """HOME NETWORK - CCNA project (Packet Tracer 9.0)
A two floor house with one router, two switches and the things a
family plugs in: PCs, laptops, smart TVs, game consoles, speakers,
cameras, a video doorbell, a thermostat and a smart fridge.

WHAT THIS LAB DOES
- one router (HOME-RTR) does everything a home router does: the
  gateway of every VLAN, DHCP, NAT to the internet and the firewall
- keeps the family, the smart home things and guests apart in
  their own VLANs, with ACLs that decide who can reach what
- one switch per floor, connected by a trunk up the stairs"""),

    ("left", """VLANS AND SUBNETS (gateway is always .1 on HOME-RTR)
10  FAMILY       192.168.10.0/24   PCs, laptops, printer
20  SMART-HOME   192.168.20.0/24   TVs, consoles, speakers, cameras,
                                   doorbell, thermostat, fridge
30  GUEST        192.168.30.0/24   the guest room
99  MGMT         192.168.99.0/24   SW-DOWN .2, SW-UP .3
998 unused ports (shut down), 999 native VLAN of the trunks"""),

    ("left", """WHO CAN REACH WHAT (ACLs on the subinterfaces of HOME-RTR)
Family:      everything in the house and the internet
Smart home:  the internet, answers to the family. A hacked camera
             cannot start a connection to a family PC
Guest:       only the internet, nothing in the house
Internet:    only answers to what the house asked for"""),

    ("right", """THINGS TO TRY (wait a minute after opening for green links)
FAMILY-PC: ipconfig -> 192.168.10.x, gateway 192.168.10.1
FAMILY-PC: ping the address of SMART-TV works (ipconfig on SMART-TV)
SMART-TV: ping FAMILY-PC fails, ping 8.8.8.8 works
GUEST-LAPTOP: ping 8.8.8.8 works, ping FAMILY-PC fails
FAMILY-PC: browser to 198.51.100.10 (the web server on the internet)
HOME-RTR: show ip nat translations, show ip dhcp binding
FAMILY-PC: ssh -l admin 192.168.99.2 (after crypto key generate rsa)"""),

    ("right", """LOGINS (router, both switches and the ISP, console included)
user admin / HomeAdmin, enable secret HomeEnable"""),

    ("right", """WHY THE THINGS ARE PCs
Packet Tracer has no smart TV, fridge or doorbell, so each one is a
PC with its own picture. It gets an address by DHCP and answers ping
like the real thing. Click one: Desktop > Command Prompt."""),

    ("info", """HOW A PACKET GETS OUT (FAMILY-PC opens 198.51.100.10)
1. FAMILY-PC asks for an address. HOME-RTR answers (ip dhcp pool FAMILY)
2. The PC sends to its gateway 192.168.10.1, subinterface Gi0/0.10
   (one cable, a trunk: router on a stick)
3. HOME-RTR swaps 192.168.10.x for its public address 203.0.113.2 (PAT)
   and sends it to the ISP. The answer comes back the same way."""),

    ("info", """SWITCHES (2960) - SW-DOWN and SW-UP
Port security (sticky, 2 MACs), PortFast + BPDU guard, DHCP snooping.
Unused ports are shut down in VLAN 998. Trunks carry 10,20,30,99 only,
native VLAN 999, no DTP. SSH only, from FAMILY and MGMT (access-class 10)."""),
]


def positions():
    return plan().where


def boxes():
    """Floors and walls first (they never overlap), then the furniture."""
    p = plan()
    return p.floors + p.walls + p.extras


def notes():
    return plan().notes


# ---------------------------------------------------------------- writing it into the file

def escape(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def shape_xml(kind, number, box, outlined=False):
    """A RECTANGLE or an ELLIPSE."""
    left, top, right, bottom, (red, green, blue) = box
    cluster = "RECTCLUSTERID" if kind == "RECTANGLE" else "ELLIPSECLUSTERID"
    # Packet Tracer saves the bottom right corner under the name TopLeft and the other way round
    return f"""<{kind} uuid="{{{uuid.uuid4()}}}">
    <TopLeftX>{right}</TopLeftX>
    <TopLeftY>{bottom}</TopLeftY>
    <BottomRightX>{left}</BottomRightX>
    <BottomRightY>{top}</BottomRightY>
    <Color>
     <Red>{red}</Red>
     <Green>{green}</Green>
     <Blue>{blue}</Blue>
    </Color>
    <Filled OUTLINECOLOR="#000000" OUTLINED="{'true' if outlined else 'false'}">1</Filled>
    <{cluster}>1-1</{cluster}>
    <MEM_ADDR>{140200000000000 + number * 4096}</MEM_ADDR>
    <DevicePlacement_ShapeName />
    <DevicePlacement_ShapeX>{(left + right) / 2:.1f}</DevicePlacement_ShapeX>
    <DevicePlacement_ShapeY>{(top + bottom) / 2:.1f}</DevicePlacement_ShapeY>
    <DevicePlacement_ShapeZ>0.21</DevicePlacement_ShapeZ>
   </{kind}>"""


def icon_path(kind):
    """The name a picture has inside the lab file. It only has to be the same in the list of
    pictures and on the device, there is no such file on the disk."""
    return f"C:/home-lab/{kind}.png"


def pictures_xml():
    """The pictures of pkticons.py, the way Packet Tracer keeps pictures inside a .pkt file."""
    images = "".join(f"""
  <IMAGE>
   <IMAGE_PATH>{icon_path(kind)}</IMAGE_PATH>
   <IMAGE_CONTENT>{base64.b64encode(pkticons.png(kind)).decode()}</IMAGE_CONTENT>
  </IMAGE>""" for kind in pkticons.ICONS)
    return f"<PIXMAPBANK>{images}\n </PIXMAPBANK>"


def note_xml(number, note):
    x, y, text = note
    return f"""<NOTE uuid="{{{uuid.uuid4()}}}">
     <X>{x}</X>
     <Y>{y}</Y>
     <Z>{40000 + 3 * number}</Z>
     <TEXT translate="true">{escape(text)}</TEXT>
     <NOTECLUSTERID>1-1</NOTECLUSTERID>
     <MEM_ADDR>{140210000000000 + number * 4096}</MEM_ADDR>
    </NOTE>"""


def description_html():
    """The same text as the notes, for the lab description window."""
    paragraph = '<p style=" margin-top:0px; margin-bottom:8px; margin-left:0px; margin-right:0px; ' \
                '-qt-block-indent:0; text-indent:0px;">'
    body = ""
    for text in plan().all_notes:
        title, _, rest = text.partition("\n")
        body += f'{paragraph}<span style=" font-weight:700;">{escape(title)}</span><br />' + \
                escape(rest).replace("\n", "<br />") + "</p>\n"
    return ('<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0//EN" "http://www.w3.org/TR/REC-html40/strict.dtd">\n'
            '<html><head><meta name="qrichtext" content="1" /><meta charset="utf-8" /><style type="text/css">\n'
            'p, li { white-space: pre-wrap; }\n</style></head>'
            '<body style=" font-family:\'Verdana\'; font-size:11pt; font-weight:400; font-style:normal;">\n'
            + body + '</body></html>')


def replace_once(xml, pattern, new_text, what):
    """Swap the one place in the file that matches, or stop if the file looks different."""
    result, count = re.subn(pattern, lambda match: new_text, xml, count=1, flags=re.S)
    if count != 1:
        raise Problem(f"Cannot find the {what} in the lab file, nothing was changed.")
    return result


def arrange(lab_path=LAB, write=True, backup=True):
    """Returns the lines of a short report. backup=False when the caller already kept a copy."""
    try:
        xml = pktfile.read_pkt(lab_path).decode("utf-8")
    except FileNotFoundError:
        raise Problem(f"Lab file not found: {lab_path}")
    except (ValueError, OSError) as err:
        raise Problem(f"Cannot read {os.path.basename(lab_path)}: {err}")

    drawn = plan()
    where = drawn.where
    kinds = {row["name"]: row["type"] for row in inventory()}
    report = []
    seen = set()

    def move(match):
        device = match.group(0)
        name = html.unescape(re.search(r"<NAME[^>]*>([^<]*)</NAME>", device).group(1))
        spot = re.search(r"(<LOGICAL>\s*<X>)([^<]*)(</X>\s*<Y>)([^<]*)(</Y>)", device)
        if name not in where or not spot:
            report.append(f"{name} is not in the layout, it stays where it is.")
            return device
        seen.add(name)
        x, y = where[name]
        if (round(float(spot.group(2))), round(float(spot.group(4)))) != (x, y):
            report.append(f"{name:<18} {spot.group(2):>5},{spot.group(4):<5} -> {x},{y}")
        device = device[:spot.start()] + f"{spot.group(1)}{x}{spot.group(3)}{y}{spot.group(5)}" + device[spot.end():]
        # a thing that is not a computer gets its own picture
        picture = icon_path(kinds[name]) if kinds.get(name) in pkticons.ICONS else ""
        return re.sub(r"<CUSTOM_IMAGE_LOGICAL>[^<]*</CUSTOM_IMAGE_LOGICAL>|<CUSTOM_IMAGE_LOGICAL />",
                      f"<CUSTOM_IMAGE_LOGICAL>{picture}</CUSTOM_IMAGE_LOGICAL>" if picture else "<CUSTOM_IMAGE_LOGICAL />",
                      device, count=1)

    xml = re.sub(r"<DEVICE>.*?</DEVICE>", move, xml, flags=re.S)
    moved = len(report)
    for name in sorted(set(where) - seen):
        report.append(f"{name} is in the layout but not in the lab.")

    all_boxes = "\n   ".join(shape_xml("RECTANGLE", i, b) for i, b in enumerate(boxes()))
    all_ovals = "\n   ".join(shape_xml("ELLIPSE", 5000 + i, b) for i, b in enumerate(drawn.ovals))
    all_notes = "\n    ".join(note_xml(i, n) for i, n in enumerate(drawn.notes))
    xml = replace_once(xml, r"\n <RECTANGLES>.*?</RECTANGLES>|\n <RECTANGLES />",
                       f"\n <RECTANGLES>\n   {all_boxes}\n  </RECTANGLES>", "coloured boxes")
    xml = replace_once(xml, r"\n <ELLIPSES>.*?</ELLIPSES>|\n <ELLIPSES />",
                       f"\n <ELLIPSES>\n   {all_ovals}\n  </ELLIPSES>", "round shapes")
    xml = replace_once(xml, r"<PIXMAPBANK>.*?</PIXMAPBANK>|<PIXMAPBANK />", pictures_xml(), "list of pictures")
    xml = replace_once(xml, r"(?<=</GRID_COLOR>)(\s*)(?:<NOTES>.*?</NOTES>|<NOTES />)",
                       f"\n   <NOTES>\n    {all_notes}\n    </NOTES>", "canvas notes")
    xml = replace_once(xml, r"(?<=<SHAPETESTS />)(\s*)<DESCRIPTION translate=\"true\">.*?</DESCRIPTION>",
                       f'\n   <DESCRIPTION translate="true">{escape(description_html())}</DESCRIPTION>',
                       "lab description")
    report.append(f"{moved} device(s) moved, {len(boxes())} boxes, {len(drawn.ovals)} round shapes, "
                  f"{len(drawn.notes)} notes, {len(pkticons.ICONS)} pictures, description written.")

    if write:
        kept = backup_lab(lab_path) if backup else None
        pktfile.write_pkt(lab_path + ".tmp", xml.encode("utf-8"))
        os.replace(lab_path + ".tmp", lab_path)
        report.append(f"Written to {os.path.basename(lab_path)}." +
                      (f" The file from before is in changes/backups/{kept}" if kept else ""))
        if packet_tracer_is_open():
            report.append("Note: Packet Tracer is running. If this lab is open in it, close the lab WITHOUT "
                          "saving and open it again.")
    else:
        report.append("Dry run, nothing was written.")
    return report



def main(args):
    lab_path = LAB
    if "--lab" in args:
        at = args.index("--lab")
        if at + 1 >= len(args):
            print("--lab needs a file name")
            return 2
        lab_path = args[at + 1]
        args = args[:at] + args[at + 2:]
    if args not in ([], ["--dry-run"]):
        print(__doc__)
        return 2
    try:
        print("\n".join(arrange(lab_path, write=not args)))
    except Problem as err:
        print("Problem:", err)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
