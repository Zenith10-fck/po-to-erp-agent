"""Synthetic ERP master data for the test set (Part A).

Everything here is invented. The story company is "Northfield Industrial Supply",
a made-up US industrial supplier. No real company, person or street address.

The data is deterministic: the same SEED always gives the same CSV files.
File layout: see docs/master-data-spec.md.
"""
from __future__ import annotations

import csv
import pathlib
import random
import re
from decimal import Decimal, ROUND_HALF_UP

from rapidfuzz import fuzz

SEED = 20261001
N_ITEMS = 300

SUPPLIER = {
    "name": "Northfield Industrial Supply",
    "address_lines": ["1200 Commerce Pkwy", "Columbus, OH 43215"],
}

PRICE_LISTS = {"PL-A": Decimal("1.00"), "PL-B": Decimal("1.04"), "PL-C": Decimal("0.97")}

CENT = Decimal("0.01")


def money(value) -> Decimal:
    """Round to 2 decimals, half up."""
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Customers (written by hand so the near-identical pairs are on purpose)
# ---------------------------------------------------------------------------
# name, aliases, street, city, state, zip, price list, number of ship-tos,
# customer-part prefix (or None), has carrier accounts, bill-to is its own AP address
_CUSTOMERS = [
    ("Harlow Fastener Supply Inc.", ["Harlow Fastener", "Harlow"], "410 Mill Road", "Dayton", "OH", "45402", "PL-A", 4, "MRO-", False, False),
    ("Pinecrest Hydraulics Corp.", ["Pinecrest Hydraulics", "PHC"], "92 Gantry Way", "Toledo", "OH", "43604", "PL-B", 3, "MRO-", True, False),
    ("Dunmore Fabrication Co.", ["Dunmore Fabrication", "Dunmore Fab"], "1705 Ironworks Blvd", "Fort Wayne", "IN", "46802", "PL-A", 5, "DF", True, False),
    ("Kessler Machine Works", ["KMW"], "1450 Foundry Rd", "Akron", "OH", "44301", "PL-B", 2, None, False, False),
    ("Kessler Machine Works East", ["KMW East"], "2875 Eastgate Pkwy", "Akron", "OH", "44301", "PL-B", 1, None, False, False),
    ("Redfern Packaging Systems LLC", ["Redfern Packaging", "RPS"], "33 Cannery Ave", "Grand Rapids", "MI", "49503", "PL-C", 2, "RP-", False, False),
    ("Oakhaven Conveyor Co.", ["Oakhaven Conveyor", "Oakhaven"], "608 Trestle Rd", "Lima", "OH", "45801", "PL-A", 1, None, True, False),
    ("Ironvale Welding Supply", ["Ironvale Welding", "Ironvale"], "254 Smelter Way", "Erie", "PA", "16501", "PL-C", 2, "IV", False, False),
    ("Tallgrass Equipment Rental Inc.", ["Tallgrass Equipment", "Tallgrass Rental"], "500 Ledger Ct Suite 200", "Peoria", "IL", "61602", "PL-B", 4, None, True, True),
    ("Copperline Electric Contractors", ["Copperline Electric", "Copperline"], "77 Switchyard Rd", "Kalamazoo", "MI", "49007", "PL-A", 1, None, True, False),
    ("Larkspur Food Machinery Ltd.", ["Larkspur Machinery", "LFM"], "1120 Granary Rd", "Madison", "WI", "53703", "PL-C", 3, None, False, False),
    ("Granite Peak Mining Services", ["Granite Peak", "GPMS"], "9 Quarry Ln", "Duluth", "MN", "55802", "PL-B", 1, None, False, False),
    ("Bluestem Agri Parts Inc.", ["Bluestem Agri", "Bluestem"], "3310 Sawmill Rd", "Des Moines", "IA", "50309", "PL-A", 2, "TP-", False, False),
    ("Halvorsen Marine Repair LLC", ["Halvorsen Marine", "HMR"], "18 Ropewalk Ln Suite 4", "Sandusky", "OH", "44870", "PL-B", 5, "HM", True, True),
    ("Westmark Plastics Inc.", ["Westmark Plastics", "Westmark"], "2460 Kiln St", "Evansville", "IN", "47708", "PL-C", 3, None, True, False),
    ("Brightwater Tool & Die LLC", ["BTD"], "615 Lathe St", "Rockford", "IL", "61101", "PL-A", 2, None, False, False),
    ("Brightwater Tool & Supply LLC", ["BTS"], "1299 Anvil Dr", "Rockford", "IL", "61101", "PL-A", 1, None, False, False),
    ("Thornbury Steel Erectors", ["Thornbury Steel", "Thornbury"], "840 Boiler Ave", "Youngstown", "OH", "44503", "PL-B", 2, "TP-", False, False),
    ("Maplewick Furniture Mfg.", ["Maplewick Furniture", "Maplewick"], "57 Loomis Ct", "Holland", "MI", "49423", "PL-C", 1, None, True, False),
    ("Cinderford Foundry Co.", ["Cinderford Foundry", "Cinderford"], "2001 Depot St", "Canton", "OH", "44702", "PL-A", 2, "CF-", False, False),
    ("Sablewood Cabinet Co.", ["Sablewood Cabinet", "Sablewood"], "300 Tannery Row Suite 12", "Elkhart", "IN", "46516", "PL-B", 4, None, True, True),
    ("Ravenglass Bottling Co.", ["Ravenglass Bottling", "Ravenglass"], "715 Commerce Dr", "Green Bay", "WI", "54301", "PL-C", 3, "RB", False, False),
    ("Fennimore Auto Body Supply", ["Fennimore Auto Body", "Fennimore"], "46 Mill Road", "Springfield", "IL", "62701", "PL-A", 1, None, False, False),
    ("Quillfeather Printing Works", ["Quillfeather Printing", "Quillfeather"], "1388 Depot St", "Cedar Rapids", "IA", "52401", "PL-B", 2, None, True, False),
    ("Stonebridge Elevator Service", ["Stonebridge Elevator", "Stonebridge"], "220 Gantry Way", "South Bend", "IN", "46601", "PL-C", 1, None, False, False),
]

# The two near-identical pairs (customer ids). Used by the R02 trap and by tests.
NEAR_IDENTICAL_PAIRS = [("C0004", "C0005"), ("C0016", "C0017")]

# Pairs of customers that share one customer_part_no string for two different items.
# The third value is the item-number parity of the two items (so each test split,
# which uses even or odd item numbers, has one such case to work with).
PART_COLLISIONS = [("C0001", "C0002", 0), ("C0013", "C0018", 1)]

_CITIES = {
    "OH": [("Dayton", "45402"), ("Toledo", "43604"), ("Akron", "44301"), ("Lima", "45801"),
           ("Sandusky", "44870"), ("Youngstown", "44503"), ("Canton", "44702"),
           ("Springfield", "45503"), ("Mansfield", "44902"), ("Findlay", "45840")],
    "IN": [("Fort Wayne", "46802"), ("Evansville", "47708"), ("Elkhart", "46516"),
           ("South Bend", "46601"), ("Kokomo", "46901"), ("Muncie", "47305")],
    "MI": [("Grand Rapids", "49503"), ("Kalamazoo", "49007"), ("Holland", "49423"),
           ("Lansing", "48933"), ("Saginaw", "48601")],
    "IL": [("Peoria", "61602"), ("Rockford", "61101"), ("Springfield", "62701"),
           ("Decatur", "62521"), ("Joliet", "60432")],
    "WI": [("Madison", "53703"), ("Green Bay", "54301"), ("Oshkosh", "54901"), ("Racine", "53403")],
    "MN": [("Duluth", "55802"), ("St. Cloud", "56301")],
    "IA": [("Des Moines", "50309"), ("Cedar Rapids", "52401"), ("Davenport", "52801")],
    "PA": [("Erie", "16501"), ("Meadville", "16335")],
}

_STREETS = ["Mill Road", "Foundry St", "Commerce Dr", "Quarry Ln", "Tannery Row", "Depot St",
            "Gantry Way", "Ironworks Blvd", "Sawmill Rd", "Cannery Ave", "Kiln St",
            "Switchyard Rd", "Loomis Ct", "Boiler Ave", "Granary Rd", "Lathe St", "Anvil Dr",
            "Trestle Rd", "Smelter Way", "Ropewalk Ln"]

_SITES = ["Plant 2", "Warehouse", "Service Center", "North Yard", "Distribution Center",
          "Maintenance Shop", "South Plant", "Tool Crib"]


# ---------------------------------------------------------------------------
# Item families: (descriptions, base uom, price low, price high, conversions)
# conversions: from_uom -> list of possible factors (base units in one from_uom)
# ---------------------------------------------------------------------------
def _families() -> list[tuple[list[str], str, str, str, dict[str, list[int]]]]:
    f = []
    metric = ["M6 x 20", "M6 x 30", "M8 x 25", "M8 x 40", "M10 x 30", "M10 x 50", "M12 x 40", "M12 x 60"]
    nuts = ["M5", "M6", "M8", "M10", "M12", "M16"]
    f.append(([f"Hex bolt {s} {fin}" for s in metric for fin in ("zinc", "stainless A2")], "EA", "0.08", "0.95", {"BX": [100], "CS": [500, 1000]}))
    f.append(([f"Hex nut {s} {fin}" for s in nuts for fin in ("zinc", "stainless A2")], "EA", "0.05", "0.40", {"BX": [100, 200], "CS": [1000]}))
    f.append(([f"Flat washer {s} {fin}" for s in nuts for fin in ("zinc", "stainless A2")], "EA", "0.05", "0.20", {"BX": [100, 200], "CS": [2000]}))
    f.append(([f"Split lock washer {s} zinc" for s in nuts[1:5]], "EA", "0.05", "0.15", {"BX": [100]}))
    f.append(([f"Nylon insert lock nut {s} zinc" for s in nuts[1:5]], "EA", "0.08", "0.35", {"BX": [100], "CS": [1000]}))
    f.append(([f"Socket head cap screw {s} black oxide" for s in ["M4 x 12", "M5 x 16", "M6 x 20", "M6 x 30", "M8 x 25", "M8 x 35", "M10 x 40", "M12 x 50"]], "EA", "0.10", "0.90", {"BX": [100], "CS": [500]}))
    f.append(([f"Self-drilling screw {s} hex washer head" for s in ["#8 x 1/2 in", "#8 x 3/4 in", "#10 x 3/4 in", "#10 x 1 in", "#12 x 1 in", "#12 x 1-1/2 in"]], "EA", "0.05", "0.15", {"BX": [250, 500], "CS": [5000]}))
    f.append(([f"Carriage bolt {s} zinc" for s in ["1/4-20 x 1 in", "1/4-20 x 2 in", "5/16-18 x 2 in", "3/8-16 x 3 in"]], "EA", "0.12", "0.70", {"BX": [50, 100]}))
    f.append(([f"Threaded rod {s} x 1 m zinc" for s in ["M8", "M10", "M12", "M16"]], "EA", "2.50", "9.00", {"PK": [10]}))
    f.append(([f"Wedge anchor {s} zinc" for s in ["3/8 x 3 in", "1/2 x 4 in", "1/2 x 5-1/2 in", "5/8 x 6 in"]], "EA", "0.60", "2.40", {"BX": [25, 50]}))
    f.append(([f"Cotter pin {s} zinc" for s in ["1/8 x 1-1/2 in", "5/32 x 2 in", "3/16 x 2-1/2 in"]], "EA", "0.05", "0.12", {"PK": [100]}))
    f.append(([f"Blind rivet aluminum {s}" for s in ["1/8 x 1/4 in", "1/8 x 3/8 in", "3/16 x 1/2 in"]], "EA", "0.05", "0.10", {"BX": [500], "CS": [5000]}))

    inch = ["1/4 in", "3/8 in", "1/2 in", "3/4 in"]
    f.append(([f"Brass compression {t} {s}" for t in ("elbow", "tee", "union", "connector") for s in inch], "EA", "1.80", "9.50", {"BX": [10], "CS": [100]}))
    f.append(([f"Brass pipe nipple {s} x 2 in" for s in inch], "EA", "1.20", "3.80", {"BX": [25]}))
    f.append(([f"JIC hydraulic adapter male {t} -{d}" for t in ("straight", "90 deg elbow") for d in ("4", "6", "8", "10", "12")], "EA", "2.20", "14.00", {"BX": [10]}))
    f.append(([f"Pneumatic quick coupler {t} {s}" for t in ("plug", "socket") for s in inch[:3]], "EA", "2.10", "8.50", {"PK": [10]}))
    f.append(([f"Ball valve {m} {s} full port" for m in ("brass", "stainless") for s in ["1/2 in", "3/4 in", "1 in", "1-1/4 in"]], "EA", "7.50", "48.00", {"BX": [6], "CS": [24]}))
    f.append(([f"Hose clamp worm drive #{s} stainless" for s in ("6", "10", "16", "24", "32", "48")], "EA", "0.45", "1.60", {"BX": [10], "CS": [100]}))
    f.append(([f"Brass hose barb {s} x 1/4 NPT" for s in ["1/4 in", "3/8 in", "1/2 in", "5/8 in"]], "EA", "0.90", "2.60", {"PK": [10, 25]}))
    f.append(([f"Grease fitting {s}" for s in ["1/4-28 straight", "1/8 NPT straight", "1/8 NPT 45 deg", "1/8 NPT 90 deg"]], "EA", "0.18", "0.65", {"PK": [10, 25], "BX": [100]}))
    f.append(([f"Steel pipe plug {s} NPT" for s in inch], "EA", "0.55", "1.90", {"BX": [25, 50]}))

    f.append(([f"Flap disc 4-1/2 in {g} grit" for g in ("40", "60", "80", "120")], "EA", "3.20", "5.50", {"BX": [10], "CS": [50, 100]}))
    f.append(([f"Cut-off wheel {s}" for s in ["4-1/2 x .045 in", "5 x .045 in", "6 x .045 in", "14 x 1/8 in chop saw"]], "EA", "1.10", "6.50", {"BX": [25], "CS": [100, 200]}))
    f.append(([f"Grinding wheel {s} depressed center" for s in ["4-1/2 x 1/4 in", "7 x 1/4 in", "9 x 1/4 in"]], "EA", "2.40", "7.90", {"BX": [10, 25]}))
    f.append(([f"Sanding belt {s} {g} grit" for s in ("3 x 21 in", "6 x 48 in") for g in ("60", "80", "120")], "EA", "1.60", "8.40", {"BX": [10]}))
    f.append(([f"Sandpaper sheet 9 x 11 in {g} grit" for g in ("80", "120", "180", "220", "320")], "EA", "0.45", "0.80", {"PK": [50], "CS": [500]}))
    f.append((["Wire cup brush 3 in knotted", "Wire cup brush 4 in knotted", "Wire wheel 6 in crimped"], "EA", "6.50", "18.00", {"BX": [6, 10]}))
    f.append(([f"Surface conditioning disc {s} {g}" for s in ("2 in", "3 in") for g in ("coarse", "medium")], "EA", "0.95", "2.20", {"BX": [25, 50]}))

    tapes = ["Duct tape 2 in x 60 yd silver", "Duct tape 2 in x 60 yd black",
             "Masking tape 1 in x 60 yd", "Masking tape 1-1/2 in x 60 yd", "Masking tape 2 in x 60 yd",
             "Electrical tape 3/4 in black", "Electrical tape 3/4 in red", "Electrical tape 3/4 in blue",
             "Electrical tape 3/4 in white", "Electrical tape 3/4 in green",
             "PTFE thread seal tape 1/2 in", "PTFE thread seal tape 3/4 in",
             "Packing tape 2 in x 110 yd clear", "Packing tape 2 in x 110 yd tan",
             "Aluminum foil tape 2 in x 50 yd", "Double-sided foam tape 3/4 in", "Double-sided foam tape 1 in",
             "Anti-slip tape 2 in black"]
    f.append((tapes, "RL", "0.65", "9.80", {"CS": [24, 36, 48], "PK": [6]}))

    sizes = ["S", "M", "L", "XL"]
    f.append(([f"Nitrile coated work gloves size {s}" for s in sizes], "PR", "2.10", "3.40", {"PK": [12], "CS": [144]}))
    f.append(([f"Leather driver gloves size {s}" for s in sizes[1:]], "PR", "9.00", "14.00", {"PK": [6], "CS": [72]}))
    f.append(([f"Cut-resistant gloves A4 size {s}" for s in sizes[1:]], "PR", "6.00", "9.00", {"PK": [12], "CS": [72]}))
    f.append((["Welding gloves 14 in size L", "Welding gloves 14 in size XL", "Knee pads gel one size"], "PR", "11.00", "19.00", {"CS": [12, 24]}))
    f.append(([f"Disposable nitrile gloves size {s} (box of 100)" for s in sizes], "EA", "8.50", "11.50", {"CS": [10]}))
    f.append(([f"Safety glasses {c} lens" for c in ("clear", "smoke", "amber")], "EA", "1.90", "4.50", {"BX": [12], "CS": [144]}))
    f.append((["Ear plugs corded (box of 100)", "Ear plugs uncorded (box of 200)", "Dust mask N95 (box of 20)"], "EA", "14.00", "26.00", {"CS": [10]}))
    f.append(([f"Hard hat {c} ratchet" for c in ("white", "yellow", "orange")], "EA", "9.50", "14.00", {"CS": [12]}))
    f.append(([f"Hi-vis safety vest size {s}" for s in ("M", "L", "XL", "2XL")], "EA", "5.00", "8.00", {"PK": [5], "CS": [25]}))
    f.append((["Face shield clear with headgear"], "EA", "12.00", "16.00", {"CS": [12]}))

    f.append(([f"HSS jobber drill bit {s}" for s in ["1/8 in", "3/16 in", "1/4 in", "5/16 in", "3/8 in", "7/16 in", "1/2 in"]], "EA", "1.40", "9.50", {"PK": [10, 12]}))
    f.append(([f"Cobalt drill bit {s}" for s in ["1/8 in", "1/4 in", "3/8 in", "1/2 in"]], "EA", "3.10", "17.50", {"PK": [6, 12]}))
    f.append(([f"Spiral point tap {s}" for s in ["M6 x 1.0", "M8 x 1.25", "M10 x 1.5", "M12 x 1.75"]], "EA", "6.80", "15.00", {"PK": [5]}))
    f.append(([f"Carbide end mill 4 flute {s}" for s in ["1/4 in", "3/8 in", "1/2 in", "3/4 in"]], "EA", "14.00", "62.00", {}))
    f.append(([f"Bi-metal hole saw {s}" for s in ["1 in", "1-1/2 in", "2 in", "2-1/2 in"]], "EA", "7.20", "15.50", {}))
    f.append(([f"Hacksaw blade 12 in {t} TPI" for t in ("18", "24", "32")], "EA", "0.95", "1.60", {"PK": [10], "BX": [100]}))
    f.append((["Reciprocating saw blade 6 in metal", "Reciprocating saw blade 9 in metal", "Reciprocating saw blade 9 in wood"], "EA", "1.80", "3.60", {"PK": [5]}))
    f.append((["Utility knife blades (dispenser of 100)", "Step drill bit 1/8 to 1/2 in", "Step drill bit 1/4 to 3/4 in",
               "Carbide burr 1/4 in cylinder", "Carbide burr 1/4 in ball", "Carbide burr 1/4 in tree"], "EA", "9.00", "24.00", {}))

    chem = ["Penetrating oil 12 oz aerosol", "Cutting fluid 1 gal", "Lithium grease cartridge 14 oz",
            "Moly grease cartridge 14 oz", "Brake parts cleaner 14 oz aerosol", "Thread locker blue 50 ml",
            "Thread locker red 50 ml", "Anti-seize compound 8 oz", "Silicone sealant clear 10 oz",
            "Silicone sealant black 10 oz", "Silicone sealant grey 10 oz", "Contact cleaner 11 oz aerosol",
            "Layout fluid blue 12 oz aerosol", "Way oil 1 gal", "Pumice hand cleaner 1 gal",
            "Marking paint orange 17 oz", "Marking paint white 17 oz", "Marking paint yellow 17 oz",
            "Cold galvanizing spray 13 oz", "Two-part epoxy 50 ml", "Dry film lubricant 11 oz aerosol",
            "Rust inhibitor 12 oz aerosol"]
    f.append((chem, "EA", "3.20", "28.00", {"CS": [6, 12]}))

    f.append(([f"MIG wire ER70S-6 {s} 33 lb spool" for s in (".030 in", ".035 in", ".045 in")], "EA", "62.00", "78.00", {}))
    f.append((["Stick electrode E6011 1/8 in", "Stick electrode E6013 3/32 in", "Stick electrode E7018 3/32 in",
               "Stick electrode E7018 1/8 in", "Stick electrode E7018 5/32 in"], "LB", "2.10", "3.60", {"BX": [10, 50]}))
    f.append((["TIG rod ER70S-2 1/16 in", "TIG rod ER70S-2 3/32 in"], "LB", "4.20", "6.10", {"BX": [10]}))
    f.append(([f"MIG contact tip {s}" for s in (".030 in", ".035 in", ".045 in")], "EA", "0.85", "1.40", {"PK": [10, 25]}))
    f.append((["MIG nozzle 1/2 in", "MIG nozzle 5/8 in", "Welding lens shade 10", "Welding lens shade 11",
               "Chipping hammer spring handle", "Tip cleaner set", "Anti-spatter spray 16 oz"], "EA", "2.40", "9.80", {"BX": [10, 12]}))

    f.append(([f"Cable tie {s} {c} (bag of 100)" for s in ("4 in", "8 in", "11 in", "14 in") for c in ("black", "natural")], "EA", "1.20", "6.80", {"CS": [10, 20, 50]}))
    f.append((["Ring terminal 16-14 AWG #10 (pack of 50)", "Ring terminal 12-10 AWG 1/4 in (pack of 50)",
               "Wire connector yellow (box of 100)", "Wire connector red (box of 100)",
               "Heat shrink tubing 1/4 in x 4 ft", "Heat shrink tubing 3/8 in x 4 ft", "Heat shrink tubing 1/2 in x 4 ft"], "EA", "2.20", "9.40", {"CS": [10, 12]}))

    hose = ["Rubber air hose 3/8 in ID", "Rubber air hose 1/2 in ID",
            "PVC clear tubing 1/4 in ID", "PVC clear tubing 3/8 in ID", "PVC clear tubing 1/2 in ID", "PVC clear tubing 3/4 in ID",
            "Polyurethane tubing 1/4 in OD blue", "Polyurethane tubing 1/4 in OD black",
            "Polyurethane tubing 3/8 in OD blue", "Polyurethane tubing 3/8 in OD black",
            "Wire rope galvanized 1/8 in", "Wire rope galvanized 3/16 in", "Wire rope galvanized 1/4 in",
            "Proof coil chain grade 30 3/16 in", "Proof coil chain grade 30 1/4 in",
            "Proof coil chain grade 30 5/16 in", "Proof coil chain grade 30 3/8 in",
            "Hydraulic hose 100R2 1/4 in", "Hydraulic hose 100R2 3/8 in", "Hydraulic hose 100R2 1/2 in"]
    f.append((hose, "FT", "0.22", "4.80", {"RL": [100, 250, 500]}))

    f.append(([f"Ball bearing 62{n:02d}-2RS" for n in range(0, 9)], "EA", "2.90", "11.50", {"BX": [10]}))
    f.append(([f"V-belt A{n}" for n in (30, 36, 42, 48, 54, 60)], "EA", "4.80", "9.20", {"PK": [5]}))
    f.append(([f"Pillow block bearing UCP{n}" for n in (204, 205, 206)], "EA", "12.50", "21.00", {}))
    f.append(([f"Roller chain #{n} 10 ft box" for n in (40, 50, 60)], "EA", "18.00", "39.00", {"CS": [5, 10]}))
    f.append(([f"Roller chain connecting link #{n}" for n in (40, 50, 60)], "EA", "0.70", "1.50", {"PK": [5, 10]}))
    f.append(([f"O-ring Buna-N dash {n}" for n in ("010", "112", "210", "214", "222", "325")], "EA", "0.05", "0.40", {"PK": [50, 100]}))
    f.append(([f"Shaft collar set screw {s}" for s in ("1/2 in", "3/4 in", "1 in")], "EA", "1.30", "3.10", {"BX": [10]}))

    f.append((["Cotton shop rags white", "Cotton shop rags mixed color", "Floor sweep compound"], "LB", "1.10", "2.40", {"BX": [25, 50]}))
    f.append((["Absorbent pad 15 x 18 in", "Oil-dry absorbent 40 lb bag", "Trash liner 55 gal (box of 100)",
               "Push broom 24 in", "Spray bottle 32 oz", "Steel funnel 1 qt"], "EA", "0.60", "22.00", {"CS": [4, 10]}))
    f.append(([f"Paint marker {c}" for c in ("yellow", "white", "red", "black")], "EA", "2.60", "3.90", {"BX": [12], "CS": [144]}))
    return f


def norm_part(text: str) -> str:
    """Part-number normal form, same rule as po_agent.normalize.norm_code."""
    return re.sub(r"[\s\-_./]", "", text or "").upper()


def _addr_tokens(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def _too_close(address: str, others: list[str]) -> bool:
    """True if `address` is so close to another ship-to of the same customer that the
    ship-to match (token_set_ratio, margin 5) could not tell them apart."""
    a = _addr_tokens(address)
    return any(fuzz.token_set_ratio(a, _addr_tokens(o)) >= 85 for o in others)


def build_master(seed: int = SEED) -> dict[str, list[dict]]:
    """Return every master table as a list of row dicts (all values are strings)."""
    rng = random.Random(seed)

    # ---- customers and ship-tos -------------------------------------------
    customers, ship_tos = [], []
    used_addresses = set()
    ship_no = 0
    for idx, (name, aliases, street, city, state, zip_code, plist, n_ship, _prefix, _carrier, own_ap) in enumerate(_CUSTOMERS, start=1):
        cid = f"C{idx:04d}"
        bill_address = f"{street}, {city}, {state} {zip_code}"
        used_addresses.add(bill_address)
        customers.append({
            "customer_id": cid, "name": name, "aliases": ";".join(aliases),
            "bill_to_id": f"B{idx:04d}", "bill_to_address": bill_address,
            "currency": "USD", "price_list_id": plist, "active": "Y",
        })
        short = name.split()[0]
        sites = rng.sample(_SITES, len(_SITES))
        own_addresses: list[str] = []
        for k in range(n_ship):
            ship_no += 1
            if k == 0 and not own_ap:
                site_name, address = f"{short} Main Plant", bill_address
            else:
                site_name = f"{short} {sites[k]}"
                while True:
                    s_city, s_zip = rng.choice(_CITIES[state])
                    address = f"{rng.randint(11, 4990)} {rng.choice(_STREETS)}, {s_city}, {state} {s_zip}"
                    if address not in used_addresses and not _too_close(address, own_addresses + [bill_address]):
                        break
                used_addresses.add(address)
            own_addresses.append(address)
            ship_tos.append({"ship_to_id": f"S{ship_no:04d}", "customer_id": cid,
                             "name": site_name, "address": address})

    # ---- items --------------------------------------------------------------
    candidates = []
    for descs, base, lo, hi, convs in _families():
        for d in descs:
            candidates.append((d, base, lo, hi, convs))
    keep = sorted(rng.sample(range(len(candidates)), N_ITEMS))
    items, conversions, base_price = [], [], {}
    legacy_used = set()
    for n, ci in enumerate(keep, start=1):
        desc, base, lo, hi, convs = candidates[ci]
        item_id = f"IT-{10000 + n}"
        legacy = ""
        if rng.random() < 0.40:
            while True:
                legacy = f"{rng.randint(10, 99)}-{rng.randint(1000, 9999)}"
                if legacy not in legacy_used:
                    break
            legacy_used.add(legacy)
        items.append({"item_id": item_id, "description": desc, "base_uom": base,
                      "legacy_item_no": legacy, "active": "Y"})
        lo_c, hi_c = int(Decimal(lo) * 100), int(Decimal(hi) * 100)
        base_price[item_id] = Decimal(rng.randint(lo_c, hi_c)) / 100
        for from_uom, factors in convs.items():
            if rng.random() < 0.80:
                conversions.append({"item_id": item_id, "from_uom": from_uom,
                                    "factor": str(rng.choice(factors))})
    for i in rng.sample(range(N_ITEMS), 8):
        items[i]["active"] = "N"
    active_ids = [it["item_id"] for it in items if it["active"] == "Y"]

    # ---- price lists (every active item, on every list, per base unit) -------
    base_uom = {it["item_id"]: it["base_uom"] for it in items}
    price_lists = []
    for plist, mult in PRICE_LISTS.items():
        for item_id in active_ids:
            price = max(money(base_price[item_id] * mult), Decimal("0.05"))
            price_lists.append({"price_list_id": plist, "item_id": item_id,
                                "uom": base_uom[item_id], "unit_price": f"{price:.2f}"})

    # ---- customer part numbers -----------------------------------------------
    parts_by_customer: dict[str, list[dict]] = {}
    for idx, row in enumerate(_CUSTOMERS, start=1):
        prefix = row[8]
        if prefix is None:
            continue
        cid = f"C{idx:04d}"
        chosen = rng.sample(active_ids, 26)
        numbers = rng.sample(range(1000, 9999), 26)
        parts_by_customer[cid] = [
            {"customer_id": cid, "customer_part_no": f"{prefix}{num}", "item_id": item_id}
            for num, item_id in zip(numbers, chosen)
        ]
    for cust_a, cust_b, parity in PART_COLLISIONS:
        def _pick(cid, other_item=None):
            for row in parts_by_customer[cid]:
                if int(row["item_id"][3:]) % 2 == parity and row["item_id"] != other_item:
                    return row
            raise RuntimeError("no part row with the wanted parity")
        row_a = _pick(cust_a)
        row_b = _pick(cust_b, other_item=row_a["item_id"])
        # Drop any other row of B that happens to have the same number, then share it.
        parts_by_customer[cust_b] = [r for r in parts_by_customer[cust_b]
                                     if r is row_b or r["customer_part_no"] != row_a["customer_part_no"]]
        row_b["customer_part_no"] = row_a["customer_part_no"]
    customer_parts = [r for cid in sorted(parts_by_customer) for r in parts_by_customer[cid]]

    # ---- carrier accounts ------------------------------------------------------
    carrier_accounts = []
    used_acct = set()
    alnum = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789"
    for idx, row in enumerate(_CUSTOMERS, start=1):
        if not row[9]:
            continue
        cid = f"C{idx:04d}"
        for carrier in rng.sample(["UPS", "FedEx", "Lakeshore Freight"], rng.choice([1, 2])):
            while True:
                if carrier == "UPS":
                    acct = "".join(rng.choice(alnum) for _ in range(6))
                elif carrier == "FedEx":
                    acct = "".join(rng.choice("0123456789") for _ in range(9))
                else:
                    acct = "LF-" + "".join(rng.choice("0123456789") for _ in range(5))
                if acct not in used_acct and not acct.isalpha():
                    break
            used_acct.add(acct)
            carrier_accounts.append({"customer_id": cid, "carrier": carrier, "account_no": acct})

    # ---- unit aliases ----------------------------------------------------------
    alias_map = {
        "EA": ["ea", "ea.", "each", "pc", "pcs", "piece", "pieces"],
        "CS": ["cs", "case", "cases", "ctn", "carton", "cartons"],
        "BX": ["bx", "box", "boxes"],
        "PK": ["pk", "pack", "packs", "pkg"],
        "RL": ["rl", "roll", "rolls"],
        "FT": ["ft", "foot", "feet"],
        "LB": ["lb", "lbs", "pound", "pounds"],
        "PR": ["pr", "pair", "pairs"],
    }
    uom_aliases = [{"alias": a, "uom": code} for code, aliases in alias_map.items() for a in aliases]

    return {
        "customers": customers, "ship_tos": ship_tos, "items": items,
        "customer_parts": customer_parts, "uom_conversions": conversions,
        "uom_aliases": uom_aliases, "price_lists": price_lists,
        "carrier_accounts": carrier_accounts,
    }


COLUMNS = {
    "customers": ["customer_id", "name", "aliases", "bill_to_id", "bill_to_address", "currency", "price_list_id", "active"],
    "ship_tos": ["ship_to_id", "customer_id", "name", "address"],
    "items": ["item_id", "description", "base_uom", "legacy_item_no", "active"],
    "customer_parts": ["customer_id", "customer_part_no", "item_id"],
    "uom_conversions": ["item_id", "from_uom", "factor"],
    "uom_aliases": ["alias", "uom"],
    "price_lists": ["price_list_id", "item_id", "uom", "unit_price"],
    "carrier_accounts": ["customer_id", "carrier", "account_no"],
}


def write_master(out_dir: pathlib.Path, tables: dict[str, list[dict]] | None = None) -> dict[str, list[dict]]:
    """Write all tables as CSV files into out_dir and return them."""
    tables = tables or build_master()
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, columns in COLUMNS.items():
        with open(out_dir / f"{name}.csv", "w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=columns, lineterminator="\n")
            writer.writeheader()
            writer.writerows(tables[name])
    return tables


def read_master(in_dir: pathlib.Path) -> dict[str, list[dict]]:
    """Read the CSV files back (used by tests to recompute from the files)."""
    tables = {}
    for name in COLUMNS:
        with open(in_dir / f"{name}.csv", encoding="utf-8", newline="") as fh:
            tables[name] = list(csv.DictReader(fh))
    return tables


class Master:
    """Look-up helper over the tables. Used by scenarios.py and the tests."""

    def __init__(self, tables: dict[str, list[dict]] | None = None):
        t = self.tables = tables or build_master()
        self.customers = {c["customer_id"]: c for c in t["customers"]}
        self.items = {i["item_id"]: i for i in t["items"]}
        self.ship_tos: dict[str, list[dict]] = {}
        for s in t["ship_tos"]:
            self.ship_tos.setdefault(s["customer_id"], []).append(s)
        self.parts: dict[str, list[dict]] = {}
        for p in t["customer_parts"]:
            self.parts.setdefault(p["customer_id"], []).append(p)
        self.conv = {(c["item_id"], c["from_uom"]): int(c["factor"]) for c in t["uom_conversions"]}
        self.price = {(p["price_list_id"], p["item_id"]): Decimal(p["unit_price"]) for p in t["price_lists"]}
        self.carriers: dict[str, list[dict]] = {}
        for a in t["carrier_accounts"]:
            self.carriers.setdefault(a["customer_id"], []).append(a)
        self.aliases = {a["alias"]: a["uom"] for a in t["uom_aliases"]}

    def factor(self, item_id: str, uom: str) -> int | None:
        """Base units in one `uom` of this item, or None if there is no conversion."""
        if uom == self.items[item_id]["base_uom"]:
            return 1
        return self.conv.get((item_id, uom))

    def list_price(self, customer_id: str, item_id: str, uom: str) -> Decimal | None:
        """The customer's list price for one `uom` of the item."""
        factor = self.factor(item_id, uom)
        base = self.price.get((self.customers[customer_id]["price_list_id"], item_id))
        if factor is None or base is None:
            return None
        return base * factor

    def part_no(self, customer_id: str, item_id: str) -> str | None:
        for p in self.parts.get(customer_id, []):
            if p["item_id"] == item_id:
                return p["customer_part_no"]
        return None


if __name__ == "__main__":
    target = pathlib.Path(__file__).resolve().parents[1] / "master-data"
    tabs = write_master(target)
    print({k: len(v) for k, v in tabs.items()})
