#!/usr/bin/env python3
r"""
Avernum 3 (2002) - Balance Mod v3.9 transparent EXE + Town.dat patcher

Standard-library Python only. No downloads, no third-party packages.

v3.9 includes every v3.8 change plus a rebalanced Call Beast progression:

  - Call Beast summon count is now rank-sensitive and scales more slowly:
      count = spell rank + floor(B / 16)
      B~13: R1=1, R2=2, R3=3
      B=20: R1=2, R2=3, R3=4
      B=40: R1=3, R2=4, R3=5
      B=48: R1=4, R2=5, R3=6
  - Call Beast SP cost is restored to vanilla 3 SP. With multiple durable
    summons now available, the earlier 2-SP discount was no longer needed.
  - Create Illusions remains 5 SP and retains count = 1 + floor(B/8), so
    it stays the higher-volume summoning spell at large B.


  - Healing Potion: original flat heal + 18.75% max HP.
  - Healing Elixir: original flat heal + 37.5% max HP.
  - Restoration Brew: original flat heal + 37.5% max HP; curing effects untouched.
  - Energy Potion: original flat SP + 18.75% max SP.
  - Energy Elixir: original flat SP + 37.5% max SP.
  - Other positive consumables using the same healing/energy abilities are
    tiered by their existing flat restoration amount: <=25 HP / <=20 SP gets
    the low percentage; stronger items get the high percentage.
  - Implementation uses existing local helper/message blocks; no section is
    resized and no external code cave is used. One cosmetic side effect: the
    redundant "is at full health" message is suppressed when healing is
    attempted on an already-full target.

First Aid behavior from v3.7 is retained:
  - First Aid is no longer limited to once per day per character.
  - First Aid healing is restored to the VANILLA formula.
  - Regular/Fine First Aid Kit contribution is restored to vanilla.
  - Kit consumption/durability is restored to the vanilla ~30% chance.
  - The previously reduced self-harm risk is retained.
  - Reduced First Aid Kit weights from v3.4 are retained.

The patcher can now upgrade an already-modded installation:
  - If Avernum 3.exe is not the exact original, it searches the same folder
    for a verified Avernum 3.original-backup-*.exe and builds v3.8 from it.
  - If Town.dat is already patched, it searches Data for a verified
    Town.original-backup-*.dat and builds the new Town.dat from that.
  - If no suitable original/backup is found, it refuses to patch.

v3.4 item changes retained:
  - Standard + special arrow/bolt ammo: 1.0 lb -> 0.5 lb.
  - All three razordisks: 1.0 lb -> 0.5 lb.
  - First Aid Kit + Fine First Aid Kit: 2.5 lb -> 1.3 lb.
    Weight is stored in 0.1-lb units, so exact 1.25 lb cannot be represented.
  - Javelin damage die-size raised to the closest integer representation
    of about +33%:
      Cursed/Stone: 1-5  -> 1-7
      Iron:         2-10 -> 2-14
      Steel:        3-15 -> 3-21
      Blessed:      5-30 -> 5-40

The item patch uses Avernum 3's real Town.dat record layout and verifies every
expected vanilla field before writing anything.

Still not included:
  - Call Beast / Arcane Summon creature-level changes.
  - Arcane Summon-only duration scaling.
  - Roaming outdoor squad respawning.

Expected ORIGINAL EXE SHA-256:
  db72579442b2e439ca4abd028404df6ee356c6e9bd08f54f5191547aa7564b3f

Expected PATCHED EXE v3.9 SHA-256:
  15242b5f8b1e49b5c278f5a4d298bfc374eca9731b4d109f857c56fcc7063375

Usage:
  python Patch-Avernum3-Balance-v3.9.py

  python Patch-Avernum3-Balance-v3.9.py "D:\Avernum Series\Avernum 3\Avernum 3.exe"

Optional explicit Town.dat path:
  python Patch-Avernum3-Balance-v3.9.py "D:\...\Avernum 3.exe" "D:\...\Data\Town.dat"
"""

from __future__ import print_function

import glob
import hashlib
import os
import shutil
import sys
import tempfile
from datetime import datetime

EXPECTED_ORIGINAL_SHA256 = "db72579442b2e439ca4abd028404df6ee356c6e9bd08f54f5191547aa7564b3f"
EXPECTED_PATCHED_SHA256 = "15242b5f8b1e49b5c278f5a4d298bfc374eca9731b4d109f857c56fcc7063375"
EXPECTED_FILE_SIZE = 8370176

# ---------------------------------------------------------------------------
# Town.dat item table layout, reconstructed from the game's own loader.
#
# Avernum 3 reads Data\Town.dat and then reads its item table beginning at
# file offset 0xDBEA. Item records are 0x58 (88) bytes each.
#
# Numeric fields in these records are big-endian on disk. The Windows game
# byte-swaps them after loading.
# ---------------------------------------------------------------------------
ITEM_TABLE_OFFSET = 0xDBEA
ITEM_RECORD_SIZE = 0x58
ITEM_COUNT = 500

ITEM_DAMAGE_DIE_OFFSET = 0x02
ITEM_WEIGHT_OFFSET = 0x1A  # tenths of a pound

MIN_TOWN_DAT_SIZE = ITEM_TABLE_OFFSET + ITEM_RECORD_SIZE * ITEM_COUNT


def hx(text):
    return bytes.fromhex(text)


# (description, FILE offset, expected original bytes, replacement bytes)
#
# Every expected byte is checked before any file is modified.
PATCHES = [
    # ------------------------------------------------------------------
    # v3.1 spell balance
    # ------------------------------------------------------------------
    ("Bolt of Fire III: 4d4 -> 6d4",
     0x10C87, hx("04"), hx("06")),

    ("Ice Lances III: 6d4 -> 8d4",
     0x10D1B, hx("06"), hx("08")),

    ("Lightning Spray III: 6d8 -> 7d8",
     0x10E02, hx("06"), hx("07")),

    ("Fireblast III: Bd4 -> Bd5",
     0x10EAB, hx("04"), hx("05")),

    ("Arcane Blow I: Bd3 -> Bd4",
     0x10F51, hx("03"), hx("04")),

    ("Arcane Blow II: Bd4 -> Bd6",
     0x10F55, hx("04"), hx("06")),

    ("Arcane Blow III: Bd6 -> Bd9",
     0x10F59, hx("06"), hx("09")),

    ("Repel Spirit III: 4d6 -> 6d6",
     0x11127, hx("04"), hx("06")),

    ("Smite III: 4d4 -> 6d4",
     0x111FA, hx("04"), hx("06")),

    # Divine Fire III = 8d4 + 2B.
    # At B=20: 48-72 damage, 60 average.
    ("Divine Fire III: die size d8 -> d4",
     0x112A1, hx("08"), hx("04")),

    ("Divine Fire III: dice count 6 -> 8",
     0x112A5, hx("06"), hx("08")),

    ("Cloud of Blades III initial hit: Bd3 -> Bd4",
     0x113C5, hx("03"), hx("04")),

    ("Divine Retribution: +1 d10 at every rank",
     0x1152A, hx("04"), hx("05")),

    # Spray Acid:
    # vanilla ~ 3 + B/(7-rank)
    # patched:
    #   rank 1: 3 + B/3
    #   rank 2: 3 + B/2
    #   rank 3: 3 + B
    ("Spray Acid: stronger B scaling",
     0x11B29, hx("07"), hx("04")),

    # Terror: rank*B/4 -> rank*B/2
    ("Terror: division mask /4 -> /2",
     0x11CDC, hx("03"), hx("01")),

    ("Terror: division shift /4 -> /2",
     0x11CE1, hx("02"), hx("01")),

    # Fireblast target scaling: B/8 -> B/4.
    # Existing global 8-target cap stays intact.
    ("Fireblast targets: division mask B/8 -> B/4",
     0x13B86, hx("07"), hx("03")),

    ("Fireblast targets: division shift B/8 -> B/4",
     0x13B8B, hx("03"), hx("02")),

    # Divine Fire target scaling:
    # min(6, rank + floor(B/4)).
    # Same byte length as the original local target calculation.
    ("Divine Fire targets: B/4 scaling with local cap of 6",
     0x13BA0,
     hx("0F BF C0 99 83 E2 07 01 D0 C1 F8 03 01 C8 66 A3 DC C3 C6 00"),
     hx("0F BF C0 C1 F8 02 01 C8 3C 06 76 02 B0 06 66 A3 DC C3 C6 00")),

    # ------------------------------------------------------------------
    # v3.1 First Aid
    # ------------------------------------------------------------------
    ("First Aid self-harm margin: +20 -> +40",
     0x7B01D, hx("14"), hx("28")),

    # First Aid daily-use gate:
    #
    # Vanilla checks the per-character "used today" byte and only enters the
    # First Aid routine when it is zero. Changing JE -> JMP makes that same
    # existing branch unconditional. The old flag may still be set/reset by
    # vanilla code, but it no longer prevents another use.
    #
    # One-byte opcode change; same branch destination, no new code.
    ("First Aid: remove once-per-day limit",
     0x7AE61, hx("74"), hx("EB")),


    # ------------------------------------------------------------------
    # v3.1 special abilities
    # ------------------------------------------------------------------
    ("Call Spirit: stronger summon from level 16",
     0x98588, hx("14"), hx("0F")),

    ("Summon Beast ability: high tier from level 21",
     0x985AA, hx("1E"), hx("14")),

    ("Summon Beast ability: mid tier from level 11",
     0x985CB, hx("0F"), hx("0A")),

    ("Regenerate: healing die d6 -> d14",
     0x98679, hx("06"), hx("0E")),

    # Restore Energy:
    # vanilla = 6 + 3*floor(character level/5)
    # patched = 2*character level.
    # Same original instruction-block length; unused bytes become NOPs.
    ("Restore Energy: load character level into ECX",
     0x98925, hx("93"), hx("8B")),

    ("Restore Energy: replace old scaling with level*2",
     0x9892A,
     hx("B8 67 66 66 66 89 D1 F7 EA C1 E9 1F D1 FA 01 D1 8D 4C 49 06"),
     hx("01 C9 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90")),

    # ------------------------------------------------------------------
    # v3.1 spell-point costs
    # ------------------------------------------------------------------
    ("Unlock Doors SP cost: 5 -> 10",
     0xC59D7, hx("05"), hx("0A")),

    ("Healing SP cost: 2 -> 3",
     0xC59E4, hx("02"), hx("03")),

    ("Mass Healing SP cost: 5 -> 10",
     0xC59EE, hx("05"), hx("0A")),

    ("Divine Fire SP cost: 7 -> 10",
     0xC59F1, hx("07"), hx("0A")),


    # ------------------------------------------------------------------
    # v3.9: Call Beast summon-count scaling
    #
    # Vanilla Call Beast sets EBX (summon count) to 1.
    #
    # v3.9:
    #   count = spell rank + floor(B / 16)
    #
    # This deliberately scales more slowly than Create Illusions
    # (1 + floor(B/8)) and makes spell rank matter directly.
    #
    # Examples:
    #   B~13: R1=1, R2=2, R3=3
    #   B=20: R1=2, R2=3, R3=4
    #   B=40: R1=3, R2=4, R3=5
    #   B=48: R1=4, R2=5, R3=6
    #
    # The replacement consumes exactly the original local padding +
    # count assignment + rank load. No code is moved and no code cave is used.
    # ------------------------------------------------------------------
    ("Call Beast: enter local rank/Bonus count block",
     0x1164F, hx("74 3F"), hx("74 3B")),

    ("Call Beast: count = rank + floor(B/16)",
     0x1168C,
     hx("8D 44 20 00 BB 01 00 00 00 0F BF 85 1C FD FF FF"),
     hx("0F BF 85 1C FD FF FF 89 CB C1 FB 04 01 C3 90 90")),

    # ------------------------------------------------------------------
    # v3.2 NEW: player physical damage cap
    #
    # Vanilla:
    #   if damage > 199, replace it with random(191,199)
    #
    # Patched:
    #   if damage > 255, replace it with random(247,255)
    #
    # Two separate player attack paths contain the same cap logic.
    # These are scalar immediate-value substitutions only.
    # ------------------------------------------------------------------
    ("Player physical damage cap path 1: 199 -> 255",
     0xA2D4,
     hx("66 81 FF C7 00 7E 16 68 C7 00 00 00 68 BF 00 00 00"),
     hx("66 81 FF FF 00 7E 16 68 FF 00 00 00 68 F7 00 00 00")),

    ("Player physical damage cap path 2: 199 -> 255",
     0xB4DF,
     hx("66 3D C7 00 7E 14 68 C7 00 00 00 68 BF 00 00 00"),
     hx("66 3D FF 00 7E 14 68 FF 00 00 00 68 F7 00 00 00")),

    # ------------------------------------------------------------------
    # v3.2 NEW: summoning spell SP costs
    # ------------------------------------------------------------------
    ("Arcane Summon SP cost: 12 -> 8",
     0xC59E1, hx("0C"), hx("08")),

    # ------------------------------------------------------------------
    # v3.2 NEW: Slow scaling
    #
    # Vanilla B-derived contribution:
    #   floor(B/5)
    #
    # Patched:
    #   floor(3*B/10)
    #
    # This is exactly +50% to the B-derived component.
    # The replacement is the same 25-byte length and uses no new jumps.
    # ------------------------------------------------------------------
    ("Slow: B scaling +50% (B/5 -> 3B/10)",
     0x11BB1,
     hx("0F BF 95 18 FD FF FF B8 67 66 66 66 89 D1 F7 EA C1 E9 1F D1 FA 01 D1 01 CB"),
     hx("0F BF 85 18 FD FF FF 6B C0 03 99 B9 0A 00 00 00 F7 F9 01 C3 90 90 90 90 90")),


    # ------------------------------------------------------------------
    # v3.8 NEW: scalable healing / energy consumables
    #
    # The item-use dispatcher already converts consumable strength into the
    # vanilla flat amount (5 * item strength). We mark only those two item
    # calls with mode 2, which is otherwise unused by these helper routines.
    # Spells, First Aid, and Regenerate keep their existing modes.
    #
    # Healing tiers (based on the already-computed flat amount):
    #   <= 25 HP  -> +3/16 max HP = +18.75%
    #   >  25 HP  -> +3/8  max HP = +37.5%
    #
    # Energy tiers:
    #   <= 20 SP  -> +3/16 max SP = +18.75%
    #   >  20 SP  -> +3/8  max SP = +37.5%
    #
    # This makes the common potion the low tier and Elixir/Brew-strength
    # items the high tier without hard-coding item IDs.
    #
    # The arithmetic is fitted into existing local helper/message blocks;
    # no executable section changes size and no external code cave is used.
    # ------------------------------------------------------------------
    ("Healing consumables: mark item-heal calls with mode 2",
     0x8075E,
     hx("6A 00"),
     hx("6A 02")),

    ("Energy consumables: mark item-energy calls with mode 2",
     0x80824,
     hx("6A 00"),
     hx("6A 02")),

    ("Healing consumables: flat + 18.75%/37.5% max HP",
     0x78EF8,
     hx("66 39 C1 7C 38 66 83 7D 10 01 75 29 68 FC 39 4C 00 6A FF 68 FC 39 4C 00 68 00 3A 4C 00 B8 70 BF C1 00 01 F8 83 C0 02 50 68 FC 39 4C 00 E8 A6 BB 02 00 83 C4 18 8D 65 F4 5F 5E 5B 5D C3 66 01 9F 50 C0 C1 00"),
     hx("66 39 C1 7D 30 66 83 7D 10 02 75 31 0F BF 87 4E C0 C1 00 8D 04 40 C1 F8 04 66 83 FB 19 7E 02 01 C0 01 C3 EB 18 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 8D 65 F4 5F 5E 5B 5D C3 66 01 9F 50 C0 C1 00")),

    ("Energy consumables: flat + 18.75%/37.5% max SP",
     0x7A4CD,
     hx("66 8B 8F 54 C0 C1 00 66 8B 87 52 C0 C1 00 66 39 C1 7E 37 66 83 FB 01 75 29 68 FC 39 4C 00 6A FF 68 FC 39 4C 00 68 C0 3E 4C 00 B8 70 BF C1 00 01 F8 83 C0 02 50 68 FC 39 4C 00 E8 C4 A5 02 00 83 C4 18 8D 65 F4 5F 5E 5B 5D C3 66 01 B7 54 C0 C1 00"),
     hx("66 8B 8F 54 C0 C1 00 66 8B 87 52 C0 C1 00 66 39 C1 7F 2F 66 83 7D 10 02 75 30 0F BF 87 52 C0 C1 00 8D 04 40 C1 F8 04 66 83 FE 14 7E 02 01 C0 01 C6 EB 17 90 90 90 90 90 90 90 90 90 90 90 90 90 90 90 8D 65 F4 5F 5E 5B 5D C3 66 01 B7 54 C0 C1 00")),
]




# ---------------------------------------------------------------------------
# Town.dat patch manifest
#
# Canonical item IDs are the game's own 0-499 item indices.
# Each expected vanilla value is verified before Town.dat is touched.
# ---------------------------------------------------------------------------

def be16(value):
    return int(value).to_bytes(2, byteorder="big", signed=False)


def item_field_offset(item_id, field_offset):
    if not (0 <= item_id < ITEM_COUNT):
        raise ValueError("Invalid item ID: %r" % (item_id,))
    return ITEM_TABLE_OFFSET + item_id * ITEM_RECORD_SIZE + field_offset


TOWN_PATCHES = []

# All standard arrow and bolt ammunition: 1.0 lb -> 0.5 lb.
_STANDARD_AMMO = {
    99: "Cursed Arrows",
    100: "Stone Arrows",
    101: "Iron Arrows",
    102: "Steel Arrows",
    103: "Blessed Arrows",
    104: "Cursed Bolts",
    105: "Stone Bolts",
    106: "Iron Bolts",
    107: "Steel Bolts",
    108: "Blessed Bolts",
}

# Special arrow/bolt ammunition: also 1.0 lb -> 0.5 lb.
_SPECIAL_AMMO = {
    352: "Acid Arrows",
    353: "Bolts of Life",
    354: "Arrows of Light",
    355: "Acid Bolts",
}

for _item_id, _name in sorted({**_STANDARD_AMMO, **_SPECIAL_AMMO}.items()):
    TOWN_PATCHES.append((
        "%s weight: 1.0 lb -> 0.5 lb" % _name,
        item_field_offset(_item_id, ITEM_WEIGHT_OFFSET),
        be16(10),
        be16(5),
    ))

# Razordisks: 1.0 lb -> 0.5 lb.
for _item_id, _name in (
    (382, "Cursed Razordisk"),
    (383, "Razordisk"),
    (384, "Fine Razordisk"),
):
    TOWN_PATCHES.append((
        "%s weight: 1.0 lb -> 0.5 lb" % _name,
        item_field_offset(_item_id, ITEM_WEIGHT_OFFSET),
        be16(10),
        be16(5),
    ))

# First Aid Kits: 2.5 lb -> 1.3 lb.
# Weight is stored in tenths, so an exact 1.25 lb cannot be represented.
for _item_id, _name in (
    (177, "First Aid Kit"),
    (178, "Fine First Aid Kit"),
):
    TOWN_PATCHES.append((
        "%s weight: 2.5 lb -> 1.3 lb" % _name,
        item_field_offset(_item_id, ITEM_WEIGHT_OFFSET),
        be16(25),
        be16(13),
    ))

# Javelin damage.
#
# The +0x02 field is the thrown weapon's integer damage die-size. Because
# d5 * 4/3 = d6.67 is not representable, d7 is the nearest integer.
# Blessed Javelin is d6 -> d8 exactly +33.3%.
for _item_id, _name, _old_die, _new_die in (
    (84, "Cursed Javelin", 5, 7),
    (85, "Stone Javelin", 5, 7),
    (86, "Iron Javelin", 5, 7),
    (87, "Steel Javelin", 5, 7),
    (88, "Blessed Javelin", 6, 8),
):
    TOWN_PATCHES.append((
        "%s damage die: d%d -> d%d" % (_name, _old_die, _new_die),
        item_field_offset(_item_id, ITEM_DAMAGE_DIE_OFFSET),
        be16(_old_die),
        be16(_new_die),
    ))


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data):
    return hashlib.sha256(bytes(data)).hexdigest()


def choose_backup_path(path):
    directory = os.path.dirname(path)
    stem, ext = os.path.splitext(os.path.basename(path))
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    candidate = os.path.join(
        directory,
        "%s.original-backup-%s%s" % (stem, stamp, ext)
    )

    number = 1
    while os.path.exists(candidate):
        candidate = os.path.join(
            directory,
            "%s.original-backup-%s-%d%s" % (stem, stamp, number, ext)
        )
        number += 1

    return candidate


def fail(message):
    print("")
    print("ERROR:")
    print(message)
    print("")
    return 1


def validate_patch_manifest(data, patches, label):
    for name, offset, expected, replacement in patches:
        if len(expected) != len(replacement):
            raise RuntimeError(
                "%s manifest error: different byte lengths for %s"
                % (label, name)
            )

        end = offset + len(expected)
        if offset < 0 or end > len(data):
            raise RuntimeError(
                "%s manifest error: patch outside file: %s"
                % (label, name)
            )

        actual = bytes(data[offset:end])
        if actual != expected:
            raise RuntimeError(
                "%s validation failed.\n\n"
                "Patch:\n  %s\n"
                "File offset:\n  0x%X\n"
                "Expected:\n  %s\n"
                "Found:\n  %s"
                % (
                    label,
                    name,
                    offset,
                    expected.hex(" ").upper(),
                    actual.hex(" ").upper(),
                )
            )


def apply_manifest(data, patches):
    for name, offset, expected, replacement in patches:
        data[offset:offset + len(replacement)] = replacement


def write_verified_temp(directory, prefix, data, expected_hash=None):
    fd, temp_path = tempfile.mkstemp(
        prefix=prefix,
        suffix=".tmp",
        dir=directory
    )

    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass

        actual_hash = sha256_file(temp_path)

        if expected_hash is not None and actual_hash != expected_hash:
            raise RuntimeError(
                "Temporary file hash verification failed.\n"
                "Expected: %s\n"
                "Produced: %s"
                % (expected_hash, actual_hash)
            )

        return temp_path, actual_hash

    except Exception:
        try:
            os.remove(temp_path)
        except OSError:
            pass
        raise



def manifest_matches_file(path, patches, label, minimum_size=0):
    try:
        if not os.path.isfile(path):
            return False
        if minimum_size and os.path.getsize(path) < minimum_size:
            return False
        with open(path, "rb") as f:
            data = bytearray(f.read())
        validate_patch_manifest(data, patches, label)
        return True
    except Exception:
        return False


def find_original_exe_source(exe_path):
    # Prefer the target itself when it is the exact original.
    if (
        os.path.isfile(exe_path)
        and os.path.getsize(exe_path) == EXPECTED_FILE_SIZE
        and sha256_file(exe_path) == EXPECTED_ORIGINAL_SHA256
    ):
        return exe_path, False

    directory = os.path.dirname(exe_path)
    stem, ext = os.path.splitext(os.path.basename(exe_path))
    pattern = os.path.join(
        directory,
        stem + ".original-backup-*" + ext
    )

    candidates = sorted(
        glob.glob(pattern),
        key=lambda p: os.path.getmtime(p),
        reverse=True
    )

    for candidate in candidates:
        try:
            if (
                os.path.getsize(candidate) == EXPECTED_FILE_SIZE
                and sha256_file(candidate) == EXPECTED_ORIGINAL_SHA256
            ):
                return candidate, True
        except OSError:
            pass

    return None, False


def find_original_town_source(town_path):
    # Town.dat can differ between distributions, so verify the actual vanilla
    # fields we patch rather than requiring one global hash.
    if manifest_matches_file(
        town_path, TOWN_PATCHES, "Town.dat", MIN_TOWN_DAT_SIZE
    ):
        return town_path, False

    directory = os.path.dirname(town_path)
    stem, ext = os.path.splitext(os.path.basename(town_path))
    pattern = os.path.join(
        directory,
        stem + ".original-backup-*" + ext
    )

    candidates = sorted(
        glob.glob(pattern),
        key=lambda p: os.path.getmtime(p),
        reverse=True
    )

    for candidate in candidates:
        if manifest_matches_file(
            candidate, TOWN_PATCHES, "Town.dat backup", MIN_TOWN_DAT_SIZE
        ):
            return candidate, True

    return None, False


def main():
    if len(sys.argv) > 3:
        return fail(
            'Usage: python "%s" ["path to Avernum 3.exe"] ["path to Town.dat"]'
            % os.path.basename(sys.argv[0])
        )

    exe_arg = sys.argv[1] if len(sys.argv) >= 2 else "Avernum 3.exe"
    exe_path = os.path.abspath(exe_arg)
    game_dir = os.path.dirname(exe_path)

    if len(sys.argv) >= 3:
        town_path = os.path.abspath(sys.argv[2])
    else:
        town_path = os.path.join(game_dir, "Data", "Town.dat")

    if not os.path.isfile(exe_path):
        return fail("EXE target not found:\n  %s" % exe_path)

    if not os.path.isfile(town_path):
        return fail(
            "Town.dat target not found:\n  %s\n\n"
            "The item changes live in Data\\Town.dat. Nothing was changed."
            % town_path
        )

    # ------------------------------------------------------------------
    # Resolve VERIFIED ORIGINAL SOURCES.
    #
    # This permits upgrading from an older mod version without incrementally
    # patching modified bytes. We always rebuild from the original files.
    # ------------------------------------------------------------------
    exe_source, exe_from_backup = find_original_exe_source(exe_path)
    if exe_source is None:
        return fail(
            "The target EXE is not the exact original and no verified original "
            "backup was found.\n\n"
            "Expected backup pattern:\n  %s\n\n"
            "Nothing was changed."
            % os.path.join(
                game_dir,
                os.path.splitext(os.path.basename(exe_path))[0]
                + ".original-backup-*"
                + os.path.splitext(exe_path)[1]
            )
        )

    town_source, town_from_backup = find_original_town_source(town_path)
    if town_source is None:
        return fail(
            "Town.dat is already modified (or incompatible) and no verified "
            "original Town.dat backup was found.\n\n"
            "Expected backup pattern:\n  %s\n\n"
            "Nothing was changed."
            % os.path.join(
                os.path.dirname(town_path),
                os.path.splitext(os.path.basename(town_path))[0]
                + ".original-backup-*"
                + os.path.splitext(town_path)[1]
            )
        )

    original_exe_hash = sha256_file(exe_source)
    original_town_hash = sha256_file(town_source)

    with open(exe_source, "rb") as f:
        exe_data = bytearray(f.read())

    with open(town_source, "rb") as f:
        town_data = bytearray(f.read())

    # Revalidate the selected sources before doing anything.
    try:
        validate_patch_manifest(exe_data, PATCHES, "original EXE")
        validate_patch_manifest(town_data, TOWN_PATCHES, "original Town.dat")
    except RuntimeError as exc:
        return fail(str(exc) + "\n\nNothing was changed.")

    print("")
    print("Verified original sources selected:")
    print("  EXE:")
    print("    %s" % exe_source)
    if exe_from_backup:
        print("    (using existing original backup)")
    print("  Town.dat:")
    print("    %s" % town_source)
    if town_from_backup:
        print("    (using existing original backup)")
    print("")

    # If the actual target itself is the original, create the usual permanent
    # original backup. If we are already using an original backup, preserve and
    # reuse it rather than creating redundant copies.
    if exe_from_backup:
        exe_backup = exe_source
    else:
        exe_backup = choose_backup_path(exe_path)
        shutil.copy2(exe_source, exe_backup)
        if sha256_file(exe_backup) != EXPECTED_ORIGINAL_SHA256:
            try:
                os.remove(exe_backup)
            except OSError:
                pass
            return fail("EXE backup verification failed. Nothing was patched.")

    if town_from_backup:
        town_backup = town_source
    else:
        town_backup = choose_backup_path(town_path)
        shutil.copy2(town_source, town_backup)
        if sha256_file(town_backup) != original_town_hash:
            try:
                os.remove(town_backup)
            except OSError:
                pass
            return fail("Town.dat backup verification failed. Nothing was patched.")

    print("Verified original backups:")
    print("  %s" % exe_backup)
    print("  %s" % town_backup)
    print("")

    print("Applying %d EXE patch entries:" % len(PATCHES))
    apply_manifest(exe_data, PATCHES)
    for name, offset, expected, replacement in PATCHES:
        print("  EXE  0x%06X  %s" % (offset, name))

    print("")
    print("Applying %d Town.dat item patch entries:" % len(TOWN_PATCHES))
    apply_manifest(town_data, TOWN_PATCHES)
    for name, offset, expected, replacement in TOWN_PATCHES:
        print("  TOWN 0x%06X  %s" % (offset, name))

    patched_exe_hash_memory = sha256_bytes(exe_data)
    if patched_exe_hash_memory != EXPECTED_PATCHED_SHA256:
        return fail(
            "Internal EXE verification failed before writing.\n"
            "Expected: %s\n"
            "Produced: %s\n"
            "Targets were not replaced."
            % (EXPECTED_PATCHED_SHA256, patched_exe_hash_memory)
        )

    # Town.dat varies between distributions. Its exact final hash is derived
    # from the validated original source and checked again after writing.
    expected_patched_town_hash = sha256_bytes(town_data)

    exe_temp = None
    town_temp = None

    try:
        exe_temp, patched_exe_hash = write_verified_temp(
            game_dir,
            "Avernum3-balance-v3.7-",
            exe_data,
            EXPECTED_PATCHED_SHA256
        )

        town_dir = os.path.dirname(town_path) or "."
        town_temp, patched_town_hash = write_verified_temp(
            town_dir,
            "Town-balance-v3.7-",
            town_data,
            expected_patched_town_hash
        )

        if os.path.getsize(exe_temp) != EXPECTED_FILE_SIZE:
            raise RuntimeError("Patched EXE temporary file has wrong size.")

        if os.path.getsize(town_temp) != len(town_data):
            raise RuntimeError("Patched Town.dat temporary file has wrong size.")

        # Replace both targets only after both temporary outputs verify.
        os.replace(town_temp, town_path)
        town_temp = None

        try:
            os.replace(exe_temp, exe_path)
            exe_temp = None
        except Exception:
            shutil.copy2(town_backup, town_path)
            raise

        final_exe_hash = sha256_file(exe_path)
        final_town_hash = sha256_file(town_path)

        if final_exe_hash != EXPECTED_PATCHED_SHA256:
            raise RuntimeError(
                "Final EXE hash verification failed after replacement."
            )

        if final_town_hash != expected_patched_town_hash:
            raise RuntimeError(
                "Final Town.dat hash verification failed after replacement."
            )

        print("")
        print("Patch completed successfully.")
        print("")
        print("Patched EXE:")
        print("  %s" % exe_path)
        print("  SHA-256: %s" % final_exe_hash)
        print("")
        print("Patched Town.dat:")
        print("  %s" % town_path)
        print("  Source SHA-256:  %s" % original_town_hash)
        print("  Patched SHA-256: %s" % final_town_hash)
        print("")
        print("Original sources/backups retained:")
        print("  %s" % exe_backup)
        print("  %s" % town_backup)
        print("")
        return 0

    except Exception as exc:
        # Restore the verified ORIGINAL sources, not an older modded version.
        try:
            shutil.copy2(exe_source, exe_path)
        except Exception:
            pass

        try:
            shutil.copy2(town_source, town_path)
        except Exception:
            pass

        return fail(
            "Patch transaction failed:\n  %s\n\n"
            "A best-effort restore from the verified original sources was "
            "attempted."
            % exc
        )

    finally:
        for temp_path in (exe_temp, town_temp):
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(130)
    except Exception as exc:
        print("")
        print("UNEXPECTED ERROR:")
        print("  %s" % exc)
        print("")
        print("If backups had already been created, they were left in place.")
        sys.exit(1)
